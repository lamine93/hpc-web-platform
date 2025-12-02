
/**
 * Alpine.js component for displaying and managing job details and the workflow timeline.
 * Data is loaded from the hidden JSON script tag with ID 'job-data'.
 */
function jobDetailsComponent() {

    const jobScript = document.getElementById('job-data');
    let jobObject = null;

    // --- 1. Chargement des Données et Initialisation Statique ---
    const workflowSteps = ['Submitted', 'Eligible', 'Scheduling', 'Running', 'Completing', 'Terminated'];

    if (jobScript) {
        try {
            jobObject = JSON.parse(jobScript.textContent) || {};
        } catch (e) {
            console.error('Failed to parse job data from #job-data script:', e);
            jobObject = { id: 0, status: 'ERROR', status_history: {} }; // Fallback minimal
        }
    } else {
        // Fallback si la balise script est absente
        jobObject = { id: 0, status: 'NOT_FOUND', status_history: {} };
    }
    const jobStatus = jobObject?.state || 'UNKNOWN';
    console.log("===current status===", jobObject);
   
    return {
        job: jobObject,
	job_status: jobStatus,
        current_status: jobStatus,
        elapsed: jobObject.elapsed_time || '0s',
        reason: jobObject.reason || 'None',
        exit_code: jobObject.exit_code || 'N/A',
        status_history: jobObject.status_history || {},

        workflowSteps: workflowSteps,

        logsOpen: false,
        logsContent: 'Loading...',

   

        isStepCompleted(step) {
            const statusUpper = this.current_status ? this.current_status.toUpperCase() : 'UNKNOWN';
            const history = this.status_history || {};
            const stepIndex = this.workflowSteps.indexOf(step);
            
            if (history.hasOwnProperty(step)) {
                return true;
            }

            if (['COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT'].includes(statusUpper)) {
                return stepIndex <= this.workflowSteps.indexOf('Completing');
            }
            
            if (statusUpper === 'RUNNING' && stepIndex <= this.workflowSteps.indexOf('Scheduling')) {
                return true;
            }
            
            if (statusUpper === 'PENDING' && stepIndex <= this.workflowSteps.indexOf('Eligible')) {
                return true;
            }
            
            const currentStepIndex = this.workflowSteps.indexOf(statusUpper);
            return stepIndex < currentStepIndex;
        },

        isStepCurrent(step) {
            const statusUpper = this.current_status ? this.current_status.toUpperCase() : 'UNKNOWN';

            if (step === 'Running') {
                return statusUpper === 'RUNNING';
            }
            if (step === 'Scheduling') {
                return statusUpper === 'PENDING';
            }
            if (step === 'Terminated') {
                return ['COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT'].includes(statusUpper);
            }
            return false;
        },

	getEstimatedCompletion() {
            const jobData = this.job;

            const startSeconds = jobData.start; 
            const limitMinutes = jobData.time_limit;

            if (jobData.status !== 'RUNNING' || !startSeconds || jobData.status_history?.End !== null) {
                return null;
            }

            if (limitMinutes === 0 || limitMinutes === Infinity) {
                return '∞'; 
            }

            try {
                const startTimeMs = startSeconds * 1000; 

                // Minutes * 60 (s/min) * 1000 (ms/s) = ms
                const limitMilliseconds = limitMinutes * 60 * 1000; 

                const completionTimeMs = startTimeMs + limitMilliseconds;
                
                const completionTime = new Date(completionTimeMs);
                
                return completionTime.toLocaleString('fr-FR');

            } catch (e) {
                return 'Error';
            }

        },

        init() {
            if (window.socket) {
                window.socket.on('job_status_update', (data) => {
                    if (data.job_id === this.job.id) {
                        this.current_status = data.status;
                        this.elapsed = data.elapsed_time;
			console.log("===current status===", this.current_status);
                    }
                });

                window.socket.on('job_logs_response', (data) => {
                    if (data.job_id === this.job?.id) {
                        this.logsContent = data.logs;
                    }
                });
            }
        },

        // --- ACTIONS ---
        // ... ( killJob, openLogsModal, closeLogsModal, requeueJob, toggleSuspendJob) ...
        async killJob() {
            if (!this.job) return;
	    const jobData = this.job;
            if (!confirm(`Confirm cancellation of the job ${this.job.id} ?`)) return;
            window.socket.emit('cancel_job', { job_id: this.job.id, action: 'kill' });
            this.current_status = 'TERMINATING';
        },

        openLogsModal() {
            if (!this.job) return;
            this.logsOpen = true;
            this.logsContent = 'Loading job output...';
            if (window.viewJobLogs) {
                window.viewJobLogs(this.job.id);
            }
        },

        closeLogsModal() {
            this.logsOpen = false;
        },

        async requeueJob() {
            if (!this.job) return;
            window.socket.emit('job_action', { job_id: this.job.id, action: 'requeue' });
            this.current_status = 'PENDING';
        },

        async toggleSuspendJob() {
            if (!this.job) return;
            const action = this.current_status === 'RUNNING' ? 'suspend' : 'resume';

            window.socket.emit('job_action', { job_id: this.job.id, action: action });
            this.current_status = (action === 'suspend' ? 'SUSPENDED' : 'RUNNING');
        }
    };
}




function viewJobLogs(jobId) {
    if (window.socket && jobId) {
        window.socket.emit('view_output', { job_id: jobId });
    } else {
        console.error("error on jobId or socket not connected.");
    }
}
window.viewJobLogs = viewJobLogs;
