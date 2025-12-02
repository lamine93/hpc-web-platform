// ============================================================================
// jobs.js
// Manages the jobs table: fetch, render, filtering, context menu & output modal.
// Uses the SocketPage helper to:
//  - wait for socket connect before first request
//  - avoid duplicate intervals across navigations
//  - pause when the tab is hidden, resume when visible
//  - trigger an immediate refresh after reconnect
// ============================================================================


// ====================================================================
// --- GLOBAL STATE AND DATA ---
// ====================================================================

// Global array that stores all active filters (the filter state)
let activeFilters = [];
// Global variable to hold the full job data set (must be loaded via API)
let jobsData = [];

// Data references for filter options (replace with dynamic loading if needed)
const availableStates = ['RUNNING', 'PENDING', 'COMPLETED', 'FAILED', 'TIMEOUT', 'CANCELLED'];
const availablePartitions = window.AVAILABLE_PARTITIONS || [];
const availableQOS = window.AVAILABLE_QOS || [];

let jobsPollId;

// Nouvelle fonction pour démarrer/redémarrer le sondage
const startJobsPolling = () => {
    const page = SocketPage('jobs');

    const requestJobs = () => {
        // ✅ NOUVEAU : Émettre get_jobs au lieu de request_jobs
        window.socket.emit('get_jobs', {
            user: window.currentUsername || null
        });
    };
    
    // Arrêter l'ancien sondage
    if (jobsPollId) {
        page.stopPoll(jobsPollId);
        page.timers.forEach(clearInterval);
        page.timers = [];
        jobsPollId = null;
    }

    // Récupérer le taux défini par l'utilisateur
    const rateMs = window.getCurrentRefreshRateMs ? window.getCurrentRefreshRateMs() : 180000;

    console.log(`[jobs] Démarrage du sondage toutes les ${rateMs / 1000} secondes.`);

    // Démarrer le nouveau sondage
    jobsPollId = page.poll(
        rateMs,
        requestJobs,
        { immediate: true, visibleOnly: true }
    );
};

$(function () {
  if (!window.socket || !window.SocketPage) {
    console.error('[jobs] Missing window.socket or SocketPage helper');
    return;
  }

  // Page-scoped socket manager
  const page = SocketPage('jobs');

  // ✅ NOUVEAU : Requête avec get_jobs
  const requestJobs = () => {
    window.socket.emit('get_jobs', {
        user: window.currentUsername || null
    });
  };

  // --- Socket listeners (deduplicated via SocketPage.on) --------------------
  page
    // ✅ NOUVEAU : Écouter jobs_list au lieu de request_jobs
    .on('jobs_list', function (response) {
      if (response.success) {
        jobsData = Array.isArray(response.jobs) ? response.jobs : [];
        console.log(`[jobs] Received ${response.count} jobs`);
        
        if (activeFilters.length !== 0) { 
          filterJobs(); // Réappliquer les filtres
        } else {
          updateJobsTable(jobsData);
        }
      } else {
        console.error('[jobs] Failed to get jobs:', response.error);
        jobsData = [];
        updateJobsTable([]);
      }
    })
    // ✅ NOUVEAU : Écouter les erreurs
    .on('error', function (data) {
      console.error('[jobs] Error:', data.message);
      showNotification('Error loading jobs: ' + data.message, 'error');
    })
    // Écouter job_submitted pour refresh automatique
    .on('job_submitted', function (data) {
      console.log('[jobs] New job submitted:', data.job_id);
      // Refresh immédiat
      requestJobs();
    })
    .on('view_output', function (outputs) {
      if (typeof Outputview === 'function') {
        Outputview(outputs);
      }
    });

  // On reconnect, trigger an immediate refresh
  page.onReconnect(() => {
    requestJobs();
  });

  // Démarrer le polling
  startJobsPolling();
  page.markStarted();

  // --- Filters wiring (safe if elements are missing) ------------------------
  const stateFilterEl = document.getElementById('stateFilter');
  const userFilterEl  = document.getElementById('userFilter');
  if (stateFilterEl) stateFilterEl.addEventListener('change', filterJobs);
  if (userFilterEl)  userFilterEl.addEventListener('input',  filterJobs);

  // --- Click outside the table: close context menu & clear selection --------
  $(document).on('click', function (event) {
    if (!$(event.target).closest('#jobs').length) {
      $('#contextMenu').hide();
      $('.selectable').removeClass('selected');
    }
  });

  // --- While scrolling: close menu & clear selection ------------------------
  window.addEventListener('scroll', function () {
    $('#contextMenu').hide();
    $('.selectable').removeClass('selected');
  }, true);

  // --- Modal close button ---------------------------------------------------
  const closeBtn = document.querySelector('.close');
  if (closeBtn) closeBtn.onclick = closeModal;

  // --- Close modal on outside click ----------------------------------------
  window.onclick = function (event) {
    const modal = document.getElementById('outputModal');
    if (modal && event.target === modal) {
      closeModal();
    }
  };
});



// Track selected row
function OnItemSelected(element) {
    const jobId = element.attr('id');
    console.log('Selected item:', jobId);
    sessionStorage.setItem('selected_job', jobId);
}

// Activate row selection & hover styles, and handle the click redirection.
function makeSelectable() {
    $('.selectable').off('click').on('click', function (e) {

        // 1. Visual selection management
        $('.selectable').removeClass('selected');
        $(this).addClass('selected');

        // 2. Store the selected Job ID
        OnItemSelected($(this));

        /* 3. REDIRECT to the job details page
        const jobId = $(this).attr('id');
        if (jobId) {
            e.preventDefault();
            window.location.href = '/jobs/details/' + jobId;
        }*/

    });

    // Activate hover styles
    $('.selectable').off('mouseover').on('mouseover', function () {
        $(this).addClass('hover');
    });

    $('.selectable').off('mouseleave').on('mouseleave', function () {
        $(this).removeClass('hover');
    });

    // Restore previous selection if any
    const selectedJobId = sessionStorage.getItem('selected_job');
    if (selectedJobId) {
        $('.selectable').filter((_, e) => e.id == selectedJobId).addClass('selected');
    }
}

/**
 * Maps Slurm job states to Tailwind CSS classes for badge styling.
 * @param {string} state - The job state (e.g., 'RUNNING', 'FAILED').
 * @returns {string} Tailwind CSS classes for the badge.
 */
function getJobBadgeClasses(state) {
    const status = state.toUpperCase(); // Ensure case-insensitivity
    
    // Default style (for unknown/other states)
    let colorClass = "bg-gray-100 text-gray-800 dark:bg-gray-600 dark:text-gray-200";

    // Mapping based on the image and common Slurm states
    if (status === "RUNNING") {
        colorClass = "bg-green-100 text-green-800 dark:bg-green-700 dark:text-green-100";
    } else if (status === "FAILED") {
        colorClass = "bg-red-100 text-red-800 dark:bg-red-700 dark:text-red-100";
    } else if (status === "PENDING") {
        colorClass = "bg-yellow-100 text-yellow-800 dark:bg-yellow-700 dark:text-yellow-100";
    } else if (status === "TIMEOUT") {
        colorClass = "bg-orange-100 text-orange-800 dark:bg-orange-700 dark:text-orange-100";
    } else if (status === "CANCELLED") {
        colorClass = "bg-purple-100 text-purple-800 dark:bg-purple-700 dark:text-purple-100";
    } else if (status === "COMPLETED") {
        colorClass = "bg-blue-100 text-blue-800 dark:bg-blue-700 dark:text-blue-100";
    }

    return colorClass;
}



// Render jobs table
function updateJobsTable(jobs) {
  const jobsTbody = document.getElementById('jobs');
  if (!jobsTbody) return;

  if (!jobs || jobs.length === 0) {
    jobsTbody.innerHTML = `
      <tr>
        <td colspan="10" class="text-center text-gray-500 dark:text-gray-400 py-8">
          No jobs found
        </td>
      </tr>
    `;
    return;
  }

  const rows = jobs.map((job) => {
    // ✅ Adapter les champs selon Job.to_dict()
    const jobId = job.job_id || job.id || '';
    const jobName = job.name || 'N/A';
    const user = job.user || job.username || 'N/A';
    const account = job.account || '';
    const userDisplay = account ? `${user} (${account})` : user;
    const partition = job.partition || 'N/A';
    const state = job.state || job.status || 'UNKNOWN';
    const qos = job.qos || 'N/A';
    const reason = job.reason || job.state_reason || '';
    const elapsed = job.elapsed_time || job.run_time || '';
    const startTime = job.start_time || '';
    const endTime = job.end_time || '';

    const badgeClass = getJobBadgeClasses(state);

     const detailUrl = typeof jobDetailUrlTemplate !== 'undefined' 
      ? jobDetailUrlTemplate.replace('0', jobId)
      : `/slurm/jobs/${jobId}`;

    return `
      <tr id="${jobId}" class="selectable cursor-pointer hover:bg-blue-500 dark:hover:bg-blue-800 transition "onclick="window.location.href='${detailUrl}';">
        <td class="px-3 py-3.5 text-left text-sm font-medium text-gray-900 dark:text-white sm:pl-6 lg:pl-8">${jobId}</td>
        <td class="px-3 py-3.5 text-left text-sm text-gray-700 dark:text-gray-300">${jobName}</td>
        <td class="px-3 py-3.5 text-left text-sm">
          <span class="px-2 py-1 text-xs font-medium rounded ${badgeClass}">
            ${state}
          </span>
        </td>
        <td class="px-3 py-3.5 text-left text-sm text-gray-700 dark:text-gray-300">${userDisplay}</td>
        <td class="px-3 py-3.5 text-left text-sm text-gray-700 dark:text-gray-300">${partition}</td>
        <td class="px-3 py-3.5 text-left text-sm text-gray-700 dark:text-gray-300">${qos}</td>
        <td class="px-3 py-3.5 text-left text-sm text-gray-500 dark:text-gray-400">${reason}</td>
        <td class="px-3 py-3.5 text-left text-sm text-gray-700 dark:text-gray-300">${elapsed}</td>
        <td class="px-3 py-3.5 text-left text-sm text-gray-700 dark:text-gray-300">${startTime}</td>
        <td class="px-3 py-3.5 text-left text-sm text-gray-700 dark:text-gray-300">${endTime}</td>
      </tr>
    `;
  }).join('');

  jobsTbody.innerHTML = rows;
  makeSelectable();
}

/**
 * Renders the active filter badges.
 */
function renderActiveFilters() {
    const container = document.getElementById('activeFiltersContainer');
    if (!container) return;

    if (activeFilters.length === 0) {
        container.innerHTML = '';
        filterJobs();
        return;
    }

    const badgesHtml = activeFilters.map((filter, index) => `
        <span class="inline-flex items-center px-3 py-1 mr-2 mb-2 text-sm font-medium text-blue-700 bg-blue-100 rounded-full dark:bg-blue-900 dark:text-blue-200">
            ${filter.label}
            <button type="button" class="remove-filter-btn ml-2 text-blue-500 hover:text-blue-700 dark:hover:text-blue-300" data-index="${index}">
                &times;
            </button>
        </span>
    `).join('');

    container.innerHTML = badgesHtml;
    filterJobs();
}

/**
 * Removes a filter by its index.
 */
function removeFilter(index) {
    activeFilters.splice(index, 1);
    renderActiveFilters();
}

/**
 * Filters the jobs table based on active filters.
 */
function filterJobs() {
    if (activeFilters.length === 0) {
        updateJobsTable(jobsData);
        return;
    }

    const EXIT_STATES = ['FAILED', 'TIMEOUT', 'CANCELLED', 'NODE_FAIL', 'OUT_OF_MEMORY'];

    const filtered = jobsData.filter((job) => {
        return activeFilters.every((filter) => {
            const jobValue = job[filter.type];

            // 1. SPECIAL CASE: State/Status Filtering
            if (filter.type === 'state' || filter.type === 'status') {
                const stateUpper = (job.state || job.status || '').toUpperCase();
                const filterUpper = filter.value.toUpperCase();

                if (filterUpper === 'EXITED') {
                    return EXIT_STATES.includes(stateUpper);
                } else {
                    return stateUpper === filterUpper;
                }
            }

            // 2. GENERIC Text/Value Filtering Logic (Partition, QOS)
            return jobValue.toString().toLowerCase() === filter.value.toLowerCase();
        });
    });

    updateJobsTable(filtered);
}


// ====================================================================
// --- MODAL HANDLING LOGIC ---
// ====================================================================

function showModal() {
    document.getElementById('filterModal').classList.remove('hidden');
    document.getElementById('filterType').value = '';
    document.getElementById('filterValueContainer').innerHTML = '<p class="text-sm text-gray-500">Select a category first.</p>';
    document.getElementById('applyFilterBtn').disabled = true;
}

function hideModal() {
    document.getElementById('filterModal').classList.add('hidden');
}

/**
 * Loads the appropriate value selection interface based on the chosen filter type.
 */
function loadValueOptions(type) {
    const container = document.getElementById('filterValueContainer');
    container.innerHTML = '';
    
    let optionsArray = [];
    if (type === 'state') {
        optionsArray = [{value: 'EXITED', label: 'EXITED (Failed, etc.)'}, ...availableStates.map(v => ({value: v, label: v}))];
    } else if (type === 'partition') {
        optionsArray = availablePartitions.map(v => ({value: v, label: v}));
    } else if (type === 'qos') {
        optionsArray = availableQOS.map(v => ({value: v, label: v}));
    } else {
        document.getElementById('applyFilterBtn').disabled = true;
        return;
    }
    
    const selectHtml = `
        <label for="filterValue" class="block text-sm font-medium mb-1 text-gray-700 dark:text-gray-300">Value:</label>
        <select id="filterValue" class="w-full p-2 border rounded-lg bg-white dark:bg-gray-700 dark:text-white">
            <option value="">-- Select Value --</option>
            ${optionsArray.map(opt => `<option value="${opt.value}">${opt.label}</option>`).join('')}
        </select>
    `;

    container.innerHTML = selectHtml;
    document.getElementById('applyFilterBtn').disabled = true;
    
    document.getElementById('filterValue').addEventListener('change', (e) => {
        document.getElementById('applyFilterBtn').disabled = e.target.value === '';
    });
}

/**
 * Handles the logic when the 'Apply' button is clicked.
 */
function handleApplyFilter() {
    const type = document.getElementById('filterType').value;
    const valueEl = document.getElementById('filterValue');
    
    if (!type || !valueEl || valueEl.value === '') {
        return;
    }
    
    const value = valueEl.value;
    const label = `${type}: ${valueEl.options[valueEl.selectedIndex].text}`;
    
    const isDuplicate = activeFilters.some(f => f.type === type && f.value === value);
    if (isDuplicate) {
        hideModal();
        return;
    }

    activeFilters.push({ 
        type: type, 
        value: value, 
        label: label
    });

    hideModal();
    renderActiveFilters();
}

// ====================================================================
// --- INITIALIZATION AND EVENT LISTENERS ---
// ====================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Global event listener for filter removal buttons
    document.addEventListener('click', (event) => {
        const btn = event.target.closest('.remove-filter-btn');
        if (btn) {
            const index = parseInt(btn.dataset.index);
            removeFilter(index);
        }
    });

    const addBtn = document.getElementById('addFiltersBtn');
    const cancelBtn = document.getElementById('cancelFilterBtn');
    const filterTypeSelect = document.getElementById('filterType');
    const applyBtn = document.getElementById('applyFilterBtn');

    if (addBtn) addBtn.addEventListener('click', showModal);
    if (cancelBtn) cancelBtn.addEventListener('click', hideModal);
    
    if (filterTypeSelect) {
        filterTypeSelect.addEventListener('change', (e) => {
            loadValueOptions(e.target.value);
        });
    }
    
    if (applyBtn) applyBtn.addEventListener('click', handleApplyFilter);
});




function cancel() {
    const id = sessionStorage.getItem('selected_job');
    const selectedRow = document.getElementById(id);

    if (!selectedRow) return;

    const stateElement = selectedRow.querySelector('td:nth-child(3)');
    const nameElement  = selectedRow.querySelector('td:nth-child(2)');

    const state = stateElement?.textContent?.trim();
    const name  = nameElement?.textContent?.trim();

    if (!(state === 'RUNNING' || state === 'PENDING')) {
        console.log(`Job ID ${id} is not RUNNING or PENDING. State: ${state}`);
        return;
    }

    const modalHTML = `
        <div id="jobCancelModal" class="modal-backdrop">
            <div class="modal-content">
                <h3 class="modal-header">Confirmation Required</h3>
                <p class="modal-body">
                    Are you sure you want to cancel the job:<br>
                    <strong class="job-name">${name}</strong> (ID: ${id})?
                </p>
                <div class="modal-actions">
                    <button id="noBtn" class="btn btn-secondary">NO</button>
                    <button id="yesBtn" class="btn btn-primary-danger">YES, CANCEL</button>
                </div>
            </div>
        </div>
    `;

    const modalContainer = document.createElement('div');
    modalContainer.innerHTML = modalHTML;
    document.body.appendChild(modalContainer);

    const removeModal = () => document.body.removeChild(modalContainer);

    document.getElementById('yesBtn').addEventListener('click', () => {
        window.socket.emit('cancel_job', { job_id: id });
        removeModal();
    });

    document.getElementById('noBtn').addEventListener('click', removeModal);

    document.getElementById('jobCancelModal').addEventListener('click', (e) => {
        if (e.target.id === 'jobCancelModal') {
            removeModal();
        }
    });
}


function view() {
  const id = sessionStorage.getItem('selected_job');
  window.socket.emit('view_output', { job_id: id });
}

function Outputview(outputs) {
  const el = document.getElementById('outputContent');
  if (el) el.innerHTML = outputs?.html?.output || '';
  openModal();
}

function openModal() {
  const modal = document.getElementById('outputModal');
  if (modal) modal.style.display = 'block';
}

function closeModal() {
  const modal = document.getElementById('outputModal');
  if (modal) modal.style.display = 'none';
}

// Helper function to show notifications
function showNotification(message, type = 'info') {
  console.log(`[${type}] ${message}`);
  // TODO: Implement visual notification system
}