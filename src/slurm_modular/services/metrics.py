# metrics.py - Improved Version

import os
import time
import requests
import datetime
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, PyMongoError
from typing import Tuple, Optional, Dict, List
from flask_socketio import SocketIO 
import logging
from functools import lru_cache
from contextlib import contextmanager

# ============================================================================
# CONFIGURATION & LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- MongoDB Configuration ---
MONGO_HOST = os.environ.get('MONGO_HOST', 'mongodb')
MONGO_PORT = int(os.environ.get('MONGO_PORT', 27017))
MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME', 'slurm_metrics_db')
COLLECTION_NAME = 'slurm_metrics_ts'
MONGODB_ENABLED = os.environ.get('MONGODB_ENABLED', 'true').lower() == 'true'

# Connection pooling
MONGO_MAX_POOL_SIZE = int(os.environ.get('MONGO_MAX_POOL_SIZE', 10))
MONGO_TIMEOUT_MS = int(os.environ.get('MONGO_TIMEOUT_MS', 5000))

# --- Prometheus Configuration ---
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090/api/v1/query")
PROMETHEUS_TIMEOUT = int(os.environ.get("PROMETHEUS_TIMEOUT", 5))

# --- Data Retention Configuration ---
DATA_RETENTION_DAYS = int(os.environ.get('DATA_RETENTION_DAYS', 30))

# Global variables for DB connection
mongo_client = None
mongo_db = None
_mongodb_initialized = False

# ============================================================================
# QUERY DEFINITIONS
# ============================================================================

DASHBOARD_QUERIES = {
    'running_jobs': 'slurm_queue_running', 
    'pending_jobs': 'slurm_queue_pending', 
    'completed_jobs': 'slurm_queue_completed', 
    'failed_jobs': 'slurm_queue_failed', 
    'cancelled_jobs': 'slurm_queue_cancelled', 
    'allocated_nodes': 'slurm_nodes_alloc', 
    'idle_nodes': 'slurm_nodes_idle', 
    'down_nodes': 'slurm_nodes_down', 
    'drain_nodes': 'slurm_nodes_drain', 
    'total_nodes': 'slurm_nodes_alloc + slurm_nodes_idle + slurm_nodes_down'
}

# Valid metric keys for validation
VALID_METRIC_KEYS = set(DASHBOARD_QUERIES.keys())

# ============================================================================
# MONGODB CONNECTION MANAGEMENT
# ============================================================================

def init_mongodb() -> bool:
    """
    Initializes the MongoDB connection and creates the Time Series collection.
    
    Returns:
        bool: True if successful, False otherwise
    """
    global mongo_client, mongo_db, _mongodb_initialized
    
    if not MONGODB_ENABLED:
        logger.info("[DB] MongoDB is disabled via environment variable")
        return False
    
    if _mongodb_initialized and mongo_db is not None:
        logger.debug("[DB] MongoDB already initialized")
        return True
        
    try:
        logger.info(f"[DB] Connecting to MongoDB at {MONGO_HOST}:{MONGO_PORT}")
        
        # Create client with connection pooling and timeouts
        mongo_client = MongoClient(
            MONGO_HOST, 
            MONGO_PORT,
            serverSelectionTimeoutMS=MONGO_TIMEOUT_MS,
            connectTimeoutMS=MONGO_TIMEOUT_MS,
            socketTimeoutMS=MONGO_TIMEOUT_MS,
            maxPoolSize=MONGO_MAX_POOL_SIZE,
            retryWrites=True
        )
        
        # Test connection with ping
        mongo_client.admin.command('ping')
        mongo_db = mongo_client[MONGO_DB_NAME]
        
        # Create Time Series collection if it doesn't exist
        existing_collections = mongo_db.list_collection_names()
        
        if COLLECTION_NAME not in existing_collections:
            mongo_db.create_collection(
                COLLECTION_NAME,
                timeseries={
                    'timeField': 'timestamp',
                    'metaField': 'metric_type',
                    'granularity': 'seconds'
                },
                expireAfterSeconds=DATA_RETENTION_DAYS * 86400  # Auto-delete old data
            )
            logger.info(f"[DB] Created Time Series collection: {COLLECTION_NAME}")
        else:
            logger.info(f"[DB] Time Series collection exists: {COLLECTION_NAME}")
        
        # Create indexes for better query performance
        _create_indexes()
        
        _mongodb_initialized = True
        logger.info("[DB] ✅ MongoDB connection established successfully")
        return True
        
    except (ConnectionFailure, ServerSelectionTimeoutError) as e:
        logger.error(f"[DB] ❌ Failed to connect to MongoDB: {e}")
        mongo_db = None
        mongo_client = None
        _mongodb_initialized = False
        return False
        
    except Exception as e:
        logger.error(f"[DB] ❌ Unexpected error initializing MongoDB: {e}", exc_info=True)
        mongo_db = None
        mongo_client = None
        _mongodb_initialized = False
        return False


def _create_indexes():
    """Creates indexes for optimized queries"""
    if mongo_db is None:
        return
    
    try:
        # Compound index for efficient time-range queries
        mongo_db[COLLECTION_NAME].create_index([
            ('metric_type', 1),
            ('timestamp', -1)
        ], background=True)
        
        logger.info("[DB] Indexes created successfully")
    except Exception as e:
        logger.warning(f"[DB] Could not create indexes: {e}")


def close_mongodb():
    """Closes the MongoDB connection gracefully"""
    global mongo_client, mongo_db, _mongodb_initialized
    
    if mongo_client is not None:
        try:
            mongo_client.close()
            logger.info("[DB] MongoDB connection closed")
        except Exception as e:
            logger.error(f"[DB] Error closing MongoDB connection: {e}")
        finally:
            mongo_client = None
            mongo_db = None
            _mongodb_initialized = False


@contextmanager
def mongodb_operation():
    """Context manager for MongoDB operations with automatic error handling"""
    if mongo_db is None:
        yield None
        return
    
    try:
        yield mongo_db
    except PyMongoError as e:
        logger.error(f"[DB] MongoDB operation error: {e}")
        raise


def is_mongodb_connected() -> bool:
    """Check if MongoDB is connected and operational"""
    if not MONGODB_ENABLED or mongo_db is None:
        return False
    
    try:
        # Quick ping to verify connection
        mongo_client.admin.command('ping')
        return True
    except Exception:
        return False


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

@lru_cache(maxsize=32)
def _get_sampling_granularity(range_string: str) -> str:
    """
    Determines the aggregation granularity for downsampling.
    Cached for performance.
    
    Args:
        range_string: Time range like '1h', '7d', '30m'
    
    Returns:
        Granularity unit: 'second', 'minute', 'hour', or 'day'
    """
    if not range_string:
        return 'minute'
    
    # Extract the numeric part and unit
    try:
        value = int(range_string[:-1])
        unit = range_string[-1].lower()
    except (ValueError, IndexError):
        logger.warning(f"Invalid range string: {range_string}, defaulting to 'minute'")
        return 'minute'
    
    # Determine granularity based on range
    if unit == 'm':  # Minutes
        if value <= 10:
            return 'second'
        else:
            return 'minute'
    elif unit == 'h':  # Hours
        if value == 1:
            return 'minute'
        elif value <= 12:
            return 'minute'
        else:
            return 'hour'
    elif unit == 'd':  # Days
        if value == 1:
            return 'hour'
        else:
            return 'day'
    
    return 'minute'


def _get_start_date(range_string: str) -> Optional[datetime.datetime]:
    """
    Converts range string to a datetime object for MongoDB filtering.
    
    Args:
        range_string: Format like '1h', '7d', '30m'
    
    Returns:
        datetime object or None if invalid
    """
    if not range_string or len(range_string) < 2:
        logger.warning(f"Invalid range string: {range_string}")
        return None
    
    now = datetime.datetime.now(datetime.timezone.utc)
    unit = range_string[-1].lower()
    
    try:
        value = int(range_string[:-1])
    except ValueError:
        logger.error(f"Cannot parse numeric value from: {range_string}")
        return None
    
    if value <= 0:
        logger.error(f"Invalid value in range string: {value}")
        return None
    
    if unit == 'm':  # minutes
        return now - datetime.timedelta(minutes=value)
    elif unit == 'h':  # hours
        return now - datetime.timedelta(hours=value)
    elif unit == 'd':  # days
        return now - datetime.timedelta(days=value)
    else:
        logger.error(f"Unknown time unit: {unit}")
        return None


def _query_prometheus(query: str, timeout: int = PROMETHEUS_TIMEOUT) -> Optional[float]:
    """
    Queries Prometheus for a single metric.
    
    Args:
        query: PromQL query string
        timeout: Request timeout in seconds
    
    Returns:
        Metric value as float, or None if error
    """
    try:
        params = {'query': query}
        response = requests.get(PROMETHEUS_URL, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        
        if data.get('status') != 'success':
            logger.warning(f"Prometheus query unsuccessful: {data.get('error')}")
            return None
        
        result = data.get('data', {}).get('result', [])
        if result:
            value = float(result[0]['value'][1])
            return value
        
        return 0.0
        
    except requests.exceptions.Timeout:
        logger.warning(f"Prometheus query timeout for: {query}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Prometheus request error: {e}")
        return None
    except (KeyError, IndexError, ValueError) as e:
        logger.error(f"Error parsing Prometheus response: {e}")
        return None


# ============================================================================
# MAIN METRIC COLLECTION FUNCTIONS
# ============================================================================

def get_all_dashboard_metrics(socketio: Optional[SocketIO] = None) -> Tuple[Optional[Dict], Optional[str]]:
    """
    1. Fetches current metrics from Prometheus.
    2. Archives the new point in MongoDB (if enabled).
    3. Emits the point via WebSocket if socketio object is provided.
    
    Args:
        socketio: Optional Flask-SocketIO instance for real-time broadcasting
    
    Returns:
        Tuple of (metrics_dict, error_message)
    """
    frontend_timestamp = time.strftime("%H:%M:%S")
    mongo_timestamp = datetime.datetime.now(datetime.timezone.utc)
    
    current_metrics = {'timestamp': frontend_timestamp}
    metric_document = {
        "metric_type": "slurm_dashboard_metrics",
        "timestamp": mongo_timestamp,
    }
    
    # Track if any Prometheus queries failed
    prometheus_errors = []
    
    try:
        # --- 1. Collect metrics from Prometheus ---
        for key, query in DASHBOARD_QUERIES.items():
            value = _query_prometheus(query)
            
            if value is None:
                prometheus_errors.append(key)
                value = 0  # Default to 0 on error
            
            # Convert to int for consistency
            value = int(value)
            current_metrics[key] = value
            metric_document[key] = value
        
        # Log if some queries failed
        if prometheus_errors:
            logger.warning(f"Failed to query Prometheus for: {', '.join(prometheus_errors)}")
        
        # --- 2. Archive to MongoDB ---
        if is_mongodb_connected():
            try:
                with mongodb_operation() as db:
                    if db is not None:
                        db[COLLECTION_NAME].insert_one(metric_document)
                        logger.debug(f"[{frontend_timestamp}] Metrics archived to MongoDB")
            except Exception as e:
                logger.error(f"[{frontend_timestamp}] MongoDB insertion failed: {e}")
                # Don't fail the entire operation if MongoDB fails
        
        # --- 3. Emit via WebSocket (Real-Time Push) ---
        if socketio is not None:
            try:
                socketio.emit('new_metric_point', current_metrics, to='slurm')
                logger.debug(f"[{frontend_timestamp}] Metrics broadcasted via WebSocket")
            except Exception as e:
                logger.error(f"[{frontend_timestamp}] WebSocket emission failed: {e}")
        
        # Return success with potential warnings
        if prometheus_errors:
            warning_msg = f"Some metrics unavailable: {', '.join(prometheus_errors)}"
            return current_metrics, warning_msg
        
        return current_metrics, None
    
    except requests.exceptions.RequestException as e:
        error_msg = f"Error connecting to Prometheus: {e}"
        logger.error(f"[{frontend_timestamp}] {error_msg}")
        return None, error_msg
    
    except Exception as e:
        error_msg = f"Unexpected error processing metrics: {e}"
        logger.error(f"[{frontend_timestamp}] {error_msg}", exc_info=True)
        return None, error_msg


# ============================================================================
# HISTORICAL DATA RETRIEVAL
# ============================================================================

def get_metrics_history_from_db(range_string: str, downsample: bool = True) -> Optional[Dict]:
    """
    Retrieves historical data from MongoDB with optional downsampling.
    
    Args:
        range_string: Time range like '1h', '7d', '30m'
        downsample: Whether to aggregate data into buckets (reduces data points)
    
    Returns:
        Dictionary with labels and metric arrays for Chart.js, or None on error
    """
    if not is_mongodb_connected():
        logger.warning("MongoDB not connected - cannot retrieve history")
        return None
    
    start_date = _get_start_date(range_string)
    if start_date is None:
        logger.error(f"Invalid range string: {range_string}")
        return None
    
    # Build the base filter
    mongo_filter = {
        'metric_type': 'slurm_dashboard_metrics',
        'timestamp': {'$gte': start_date}
    }
    
    try:
        if downsample:
            # Use aggregation pipeline for downsampling
            return _get_downsampled_history(mongo_filter, range_string)
        else:
            # Return raw data without aggregation
            return _get_raw_history(mongo_filter)
    
    except PyMongoError as e:
        logger.error(f"MongoDB query error: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error retrieving history: {e}", exc_info=True)
        return None


def _get_downsampled_history(mongo_filter: Dict, range_string: str) -> Optional[Dict]:
    """
    Retrieves downsampled historical data using MongoDB aggregation.
    Reduces the number of data points by grouping into time buckets.
    """
    bucket_unit = _get_sampling_granularity(range_string)
    
    pipeline = [
        # 1. Filter by time range and metric type
        {'$match': mongo_filter},
        
        # 2. Group into time buckets
        {'$group': {
            '_id': {
                '$dateTrunc': {
                    'date': '$timestamp',
                    'unit': bucket_unit,
                    'binSize': 1,
                    'timezone': 'UTC'
                }
            },
            # Calculate average for each metric
            **{key: {'$avg': f'${key}'} for key in DASHBOARD_QUERIES.keys()}
        }},
        
        # 3. Sort by time
        {'$sort': {'_id': 1}},
        
        # 4. Project final fields
        {'$project': {
            '_id': 0,
            'timestamp': '$_id',
            **{key: 1 for key in DASHBOARD_QUERIES.keys()}
        }}
    ]
    
    with mongodb_operation() as db:
        if db is None:
            return None
        
        history_cursor = db[COLLECTION_NAME].aggregate(pipeline)
        history_data = list(history_cursor)
    
    logger.info(f"Retrieved {len(history_data)} downsampled data points for range {range_string}")
    return _format_history_data(history_data)


def _get_raw_history(mongo_filter: Dict) -> Optional[Dict]:
    """Retrieves raw historical data without aggregation"""
    with mongodb_operation() as db:
        if db is None:
            return None
        
        cursor = db[COLLECTION_NAME].find(mongo_filter).sort('timestamp', 1).limit(10000)
        history_data = list(cursor)
    
    logger.info(f"Retrieved {len(history_data)} raw data points")
    return _format_history_data(history_data)


def _format_history_data(history_data: List[Dict]) -> Dict:
    """
    Formats MongoDB documents into Chart.js compatible structure.
    
    Args:
        history_data: List of MongoDB documents
    
    Returns:
        Dictionary with 'labels' and metric arrays
    """
    formatted_data = {
        "labels": [],
        "count": len(history_data)
    }
    
    # Initialize arrays for each metric
    for key in DASHBOARD_QUERIES.keys():
        formatted_data[key] = []
    
    for doc in history_data:
        # Format timestamp for display
        timestamp = doc.get('timestamp')
        if isinstance(timestamp, datetime.datetime):
            doc_time = timestamp.strftime("%H:%M:%S")
        else:
            doc_time = str(timestamp)
        
        formatted_data['labels'].append(doc_time)
        
        # Add metric values (rounded to integers)
        for key in DASHBOARD_QUERIES.keys():
            value = doc.get(key, 0)
            formatted_data[key].append(int(round(value)))
    
    return formatted_data


# ============================================================================
# STATISTICS & ANALYTICS
# ============================================================================

def get_metrics_statistics(metric_key: str, range_string: str = '1h') -> Optional[Dict]:
    """
    Calculates statistics (avg, min, max, sum) for a specific metric.
    
    Args:
        metric_key: Metric name (must be in VALID_METRIC_KEYS)
        range_string: Time range like '1h', '7d'
    
    Returns:
        Dictionary with statistics or None on error
    """
    if metric_key not in VALID_METRIC_KEYS:
        logger.error(f"Invalid metric key: {metric_key}")
        return None
    
    if not is_mongodb_connected():
        logger.warning("MongoDB not connected - cannot get statistics")
        return None
    
    start_date = _get_start_date(range_string)
    if start_date is None:
        return None
    
    pipeline = [
        {
            '$match': {
                'metric_type': 'slurm_dashboard_metrics',
                'timestamp': {'$gte': start_date}
            }
        },
        {
            '$group': {
                '_id': None,
                'avg': {'$avg': f'${metric_key}'},
                'min': {'$min': f'${metric_key}'},
                'max': {'$max': f'${metric_key}'},
                'sum': {'$sum': f'${metric_key}'},
                'count': {'$sum': 1}
            }
        }
    ]
    
    try:
        with mongodb_operation() as db:
            if db is None:
                return None
            
            result = list(db[COLLECTION_NAME].aggregate(pipeline))
        
        if result:
            stats = result[0]
            return {
                "metric": metric_key,
                "range": range_string,
                "avg": round(stats.get('avg', 0), 2),
                "min": int(stats.get('min', 0)),
                "max": int(stats.get('max', 0)),
                "sum": int(stats.get('sum', 0)),
                "count": stats.get('count', 0)
            }
        
        # No data found
        return {
            "metric": metric_key,
            "range": range_string,
            "avg": 0,
            "min": 0,
            "max": 0,
            "sum": 0,
            "count": 0
        }
    
    except Exception as e:
        logger.error(f"Error calculating statistics: {e}", exc_info=True)
        return None


def get_all_metrics_summary(range_string: str = '1h') -> Optional[Dict]:
    """
    Get summary statistics for all metrics at once.
    More efficient than calling get_metrics_statistics multiple times.
    
    Args:
        range_string: Time range like '1h', '7d'
    
    Returns:
        Dictionary with statistics for all metrics
    """
    if not is_mongodb_connected():
        return None
    
    start_date = _get_start_date(range_string)
    if start_date is None:
        return None
    
    summary = {}
    
    for metric_key in VALID_METRIC_KEYS:
        stats = get_metrics_statistics(metric_key, range_string)
        if stats:
            summary[metric_key] = stats
    
    return summary


# ============================================================================
# MAINTENANCE & CLEANUP
# ============================================================================

def cleanup_old_data(days_to_keep: int = DATA_RETENTION_DAYS) -> int:
    """
    Manually remove data older than specified days.
    Note: If collection has expireAfterSeconds, this is automatic.
    
    Args:
        days_to_keep: Number of days to retain
    
    Returns:
        Number of documents deleted
    """
    if not is_mongodb_connected():
        logger.warning("MongoDB not connected - cannot cleanup")
        return 0
    
    cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_to_keep)
    
    try:
        with mongodb_operation() as db:
            if db is None:
                return 0
            
            result = db[COLLECTION_NAME].delete_many({
                'timestamp': {'$lt': cutoff_date}
            })
            
            deleted_count = result.deleted_count
            logger.info(f"Cleaned up {deleted_count} old documents (older than {days_to_keep} days)")
            return deleted_count
    
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        return 0


def get_database_info() -> Optional[Dict]:
    """
    Get information about the MongoDB collection.
    Useful for monitoring and debugging.
    
    Returns:
        Dictionary with collection stats
    """
    if not is_mongodb_connected():
        return None
    
    try:
        with mongodb_operation() as db:
            if db is None:
                return None
            
            stats = db.command('collStats', COLLECTION_NAME)
            
            return {
                'collection': COLLECTION_NAME,
                'count': stats.get('count', 0),
                'size_bytes': stats.get('size', 0),
                'avg_obj_size': stats.get('avgObjSize', 0),
                'storage_size': stats.get('storageSize', 0),
                'indexes': stats.get('nindexes', 0)
            }
    
    except Exception as e:
        logger.error(f"Error getting database info: {e}")
        return None


# ============================================================================
# MODULE INITIALIZATION
# ============================================================================

# Initialize MongoDB when module is imported
if MONGODB_ENABLED:
    init_mongodb()
else:
    logger.info("MongoDB integration is disabled")
