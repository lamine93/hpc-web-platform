// =========================================================
// dashboard.js - Architecture Hybride (MongoDB History + WebSocket Live)
// =========================================================

// --- CHART.JS SETUP ---
let jobStatusChart, jobFailureChart, nodeStatusChart, nodeDownChart;
const MAX_DATA_POINTS = 40; // Sliding window for real-time visualization
let currentRange = '1h'; // Default time range for history retrieval

// HTML Elements
const timeRangeSelect = document.getElementById('timeRange');
const errorEl = document.getElementById('metrics-error'); 

// =========================================================
// 1. UTILS & HISTORY FETCH (HTTP)
// =========================================================

const displayError = (message) => {
    if (errorEl) {
        errorEl.innerText = message || '';
        // Utilisation des classes Tailwind de votre structure
        errorEl.style.display = message ? 'block' : 'none'; 
    }
};

// const setTxt = (id, val) => {
//     // Helper function to update counters based on ID
//     const el = document.getElementById(id);
//     if (el != null && val != null) el.innerText = val;
// };
function setTxt(id, value) {
    // Assurez-vous que la valeur est affichée comme 0 si elle est null, undefined ou vide
    const displayValue = value === null || value === undefined ? 0 : value;
    console.log("value", value);
    $('#' + id).text(displayValue);
}

const fetchAllChartHistory = async () => {
    displayError(null);
    try {
        // Fetch historical data from the Flask API with the selected time range
        const response = await fetch(`/slurm/metrics/history?range=${currentRange}`);
        
        if (!response.ok) {
            throw new Error(`Server returned status ${response.status}`);
        }
        
        const data = await response.json();
        if (data.error) {
            throw new Error(data.error);
        }
        return data;
    } catch (error) {
        console.error("Error fetching chart history:", error);
        displayError(`Failed to load history for ${currentRange}: ${error.message}`);
        return null;
    }
};

const mapHistoryToChartData = (keys, defaultDatasets, historyData) => {
    if (!historyData) {
        return { labels: [], datasets: defaultDatasets };
    }

    const datasets = defaultDatasets.map((d, i) => {
        let dataArray = [];

        // Special case: Combine Down and Drain for Node Status Chart
        // We assume the Node Status Chart combines 'Down' and 'Drain/Maint' into one dataset ('Down/Drain')
        // The Python script gives us 'down_nodes' and 'drain_nodes' separately.
        if (d.label === 'Down/Drain') {
             const down = historyData['down_nodes'] || [];
             const drain = historyData['drain_nodes'] || [];
             dataArray = down.map((v, index) => v + (drain[index] || 0));
             
        } else {
             // General case: direct mapping using the key array
             dataArray = historyData[keys[i]] || [];
        }

        return {
            ...d,
            data: dataArray
        };
    });

    return {
        labels: historyData.labels || [],
        datasets: datasets
    };
};

// =========================================================
// 2. CHART DEFINITION & INITIALIZATION (Async)
// =========================================================

const initCharts = async () => {
    // 1. Get historical data from MongoDB (via HTTP fetch)
    const historyData = await fetchAllChartHistory();
    
    // --- Base Chart Configurations ---
    const chartOptions = { 
        responsive: true, 
        maintainAspectRatio: false,
        animation: false,
        scales: { y: { beginAtZero: true } }
    };
    
    const stackedOptions = {
        scales: { 
            x: { stacked: true },
            y: { beginAtZero: true, stacked: true } 
        }
    };

    // --- 1. Job Status Chart ---
    const jobStatusDefaultDatasets = [
        { label: 'Running', data: [], backgroundColor: 'rgba(75, 192, 192, 0.7)', borderColor: 'rgb(75, 192, 192)', tension: 0.3, fill: true },
        { label: 'Pending', data: [], backgroundColor: 'rgba(255, 159, 64, 0.7)', borderColor: 'rgb(255, 159, 64)', tension: 0.3, fill: true },
        { label: 'Completed', data: [], backgroundColor: 'rgba(153, 102, 255, 0.7)', borderColor: 'rgb(153, 102, 255)', tension: 0.3, fill: true }
    ];
    
    const jobStatusInitialData = mapHistoryToChartData(
        ['running_jobs', 'pending_jobs', 'completed_jobs'], 
        jobStatusDefaultDatasets,
        historyData
    );

    if (jobStatusChart) jobStatusChart.destroy();
    jobStatusChart = new Chart(document.getElementById('jobStatusChart'), {
        type: 'line',
        data: jobStatusInitialData,
        options: {...chartOptions, ...stackedOptions, plugins: { title: { display: true, text: 'Job Status (Running, Pending, Completed)' } } }
    });


    // --- 2. Job Failure Chart ---
    const jobFailureDefaultDatasets = [
        { label: 'Cancelled', data: [], backgroundColor: 'rgba(201, 203, 207, 0.7)', borderColor: 'rgb(201, 203, 207)', tension: 0.3, fill: true },
        { label: 'Failed', data: [], backgroundColor: 'rgba(255, 99, 132, 0.7)', borderColor: 'rgb(255, 99, 132)', tension: 0.3, fill: true }
    ];
    
    const jobFailureInitialData = mapHistoryToChartData(
        ['cancelled_jobs', 'failed_jobs'], 
        jobFailureDefaultDatasets,
        historyData
    );

    if (jobFailureChart) jobFailureChart.destroy();
    jobFailureChart = new Chart(document.getElementById('jobFailureChart'), {
        type: 'line',
        data: jobFailureInitialData,
        options: {...chartOptions, ...stackedOptions, plugins: { title: { display: true, text: 'Error/Cancellation Status (Failed, Cancelled)' } } }
    });

    // --- 3. Node Status Chart (Allocated, Idle, Down/Drain) ---
    const nodeStatusDefaultDatasets = [
        { label: 'Allocated', data: [], backgroundColor: 'rgba(54, 162, 235, 0.7)', borderColor: 'rgb(54, 162, 235)', tension: 0.3, fill: true },
        { label: 'Idle', data: [], backgroundColor: 'rgba(75, 192, 192, 0.7)', borderColor: 'rgb(75, 192, 192)', tension: 0.3, fill: true },
        // Down/Drain combined dataset (handled by mapHistoryToChartData)
        { label: 'Down/Drain', data: [], backgroundColor: 'rgba(255, 99, 132, 0.7)', borderColor: 'rgb(255, 99, 132)', tension: 0.3, fill: true } 
    ];

    const nodeStatusInitialData = mapHistoryToChartData(
        ['allocated_nodes', 'idle_nodes'], // Keys used for direct mapping
        nodeStatusDefaultDatasets,
        historyData
    );

    if (nodeStatusChart) nodeStatusChart.destroy();
    nodeStatusChart = new Chart(document.getElementById('nodeStatusChart'), {
        type: 'line',
        data: nodeStatusInitialData,
        options: {...chartOptions, ...stackedOptions, plugins: { title: { display: true, text: 'Node Status (Allocated, Idle, Down/Drain)' } } }
    });

    // --- 4. Node Down Chart (Drain, Down) ---
    const nodeDownDefaultDatasets = [
        { label: 'Drain/Maint', data: [], backgroundColor: 'rgba(255, 205, 86, 0.7)', borderColor: 'rgb(255, 205, 86)', tension: 0.3, fill: true },
        { label: 'Down', data: [], backgroundColor: 'rgba(255, 99, 132, 0.7)', borderColor: 'rgb(255, 99, 132)', tension: 0.3, fill: true }
    ];

    const nodeDownInitialData = mapHistoryToChartData(
        ['drain_nodes', 'down_nodes'], 
        nodeDownDefaultDatasets,
        historyData
    );
    
    if (nodeDownChart) nodeDownChart.destroy();
    nodeDownChart = new Chart(document.getElementById('nodeDownChart'), {
        type: 'line',
        data: nodeDownInitialData,
        options: {...chartOptions, ...stackedOptions, plugins: { title: { display: true, text: 'Error/Maintenance Nodes (Down, Drain)' } } }
    });
    
    // 2. Setup WebSocket connection once charts are ready
    setupWebSockets();
};


// =========================================================
// 3. REAL-TIME UPDATES (WebSocket)
// =========================================================

const updateChart = (chart, values, ts) => {
    if (!chart || !ts) return;
    
    chart.data.labels.push(ts);

    values.forEach((v, i) => {
        if (chart.data.datasets[i]) {
            chart.data.datasets[i].data.push(v);
        }
    });

    // Handle the sliding window (remove oldest points)
    if (chart.data.labels.length > MAX_DATA_POINTS) {
        chart.data.labels.shift();
        chart.data.datasets.forEach(dataset => dataset.data.shift());
    }

    chart.update();
};

const updateAllCharts = (data) => {
    // data is the JSON object pushed by the server
    const ts = data.timestamp; 
    
    displayError(null); 

    // Chart 1: Job Status
    updateChart(
        jobStatusChart,
        [data.running_jobs, data.pending_jobs, data.completed_jobs],
        ts
    );

    // Chart 2: Job Failure
    updateChart(
        jobFailureChart,
        [data.cancelled_jobs, data.failed_jobs],
        ts
    );

    // Chart 3: Node Status (Allocated, Idle, Down + Drain combined)
    updateChart(
        nodeStatusChart,
        [data.allocated_nodes, data.idle_nodes, data.down_nodes + data.drain_nodes],
        ts
    );

    // Chart 4: Node Down
    updateChart(
        nodeDownChart,
        [data.drain_nodes, data.down_nodes],
        ts
    );
    
    // Update the counter widgets using your existing IDs
    //setTxt('nodes', data.total_nodes);
    // NOTE: Prometheus metrics don't typically include 'cores' or 'total_jobs' 
    // in this specific data point, so these might remain 0 unless you pass them too.
    //setTxt('running_jobs', data.running_jobs);
    // setTxt('total_jobs', data.total_jobs); // Assuming total_jobs is calculated or available
};

const setupWebSockets = () => {
    // Rely on window.socket if you use a helper like SocketPage, otherwise use io()
    const socket = window.socket || io(); 

    socket.on('connect', () => {
        console.log('[WS] Connected to server. Live stream running.');
        displayError(null);
    });

    // Listen for the 'new_metric_point' event broadcasted by the Python background thread
    socket.on('new_metric_point', (data) => {
        updateAllCharts(data); 
    });
    
    // Listen for error messages from the server
    socket.on('metrics_response', (data) => {
        if (data.error) {
            console.error("[WS] Server error:", data.error);
            displayError(`Server Error: ${data.error}`);
        }
    });

    socket.on('disconnect', () => {
        console.log('[WS] Disconnected from server. Live updates stopped.');
        displayError("Disconnected from server. Live updates stopped.");
    });
    
    // Remove old SocketPage polling and use only the WebSocket stream and HTTP history.
    // Ensure all references to page.poll and page.on('metrics_response') are gone from the file.
};

// =========================================================
// 4. APPLICATION ENTRY POINT
// =========================================================

const handleTimeRangeChange = (newRange) => {
    if (newRange === currentRange) return;
    
    currentRange = newRange;
    // Reload charts with the new historical window
    console.log(`Time range changed to ${currentRange}. Reloading charts...`);
    initCharts(); 
};


$(function () {
    // 1. Setup the Time Range selector
    if (timeRangeSelect) {
        timeRangeSelect.value = currentRange;
        timeRangeSelect.addEventListener('change', (e) => handleTimeRangeChange(e.target.value));
    }

    // 2. Initial chart load and WebSocket setup
    //initCharts();

    const page = SocketPage('dashboard');
    const requestStats = () => {
    	console.log('[dashboard] emit stats');
    	window.socket.emit('get_stats');
    };

     // Listen to server payload
    page.on('stats_list', (data) => {
        const payload = data.stats;
        if (!Array.isArray(payload) || payload.length === 0) {
            console.error('[dashboard] error: Received an empty or malformed array.', payload);
            return;
        }
        stats = payload[0];
        console.log('[dashboard] received:', stats);

        // Support both flat payloads and payload.html for backward compatibility
        setTxt('nodes',        stats.nodes);
        setTxt('cores',        stats.cores);
        setTxt('running_jobs', stats.running_jobs);
        setTxt('total_jobs',   stats.total_jobs);

    });

     // On reconnect, trigger an immediate refresh
    page.onReconnect(() => {
   	console.log('[dashboard] reconnect → refresh now');
    	requestStats();
    });

     // Poll every 3 minutes, fire once immediately when connected,
     // and skip when the tab is hidden to save resources
     page
    	.poll(180000, requestStats, { immediate: true, visibleOnly: true })
    	.markStarted();
   
});
