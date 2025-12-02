// ============================================================================
// resources.js
// Page script using the SocketPage helper from common.js
// - waits for socket connect before first request
// - avoids duplicate intervals across navigations
// - pauses when the tab is hidden, resumes when visible
// - triggers an immediate refresh after reconnect
// ============================================================================

$(function () {
  if (!window.socket || !window.SocketPage) {
    console.error('[resources] Missing window.socket or SocketPage helper');
    return;
  }

  // Create a page-scoped socket manager
  const page = SocketPage('resources');

  // What we ask from the server
  const requestResources = () => {
    console.log('[resources] emit request_resources');
    window.socket.emit('get_resources');
  };

  // Handle server response
  page.on('resources_list', (data) => {
    console.log('[resources] received:', data);
    const resources = data.resources;
    updateResourcesTable(Array.isArray(resources) ? resources : []);
  });

  // On reconnect, immediately refresh once
  page.onReconnect(() => {
    console.log('[resources] reconnect → refresh now');
    requestResources();
  });

  // Poll every 3 minutes, fire once immediately when connected,
  // and skip when the tab is hidden to save resources
  page
    .poll(180000, requestResources, { immediate: true, visibleOnly: true })
    .markStarted();

  // --- Optional UI niceties (not related to sockets) ------------------------
  // Clear selection if clicking outside the #resources table
  $(document).on('click', (e) => {
    if (!$(e.target).closest('#resources').length) {
      $('.selectable').removeClass('selected');
    }
  });

  // Clear selection on scroll (useful on small screens)
  window.addEventListener('scroll', () => {
    $('.selectable').removeClass('selected');
  }, true);
});



// Track selection (optional to extend)
function OnItemSelected(element) {
  console.log('Selected item:', element.attr('id'));
  sessionStorage.setItem('selected_job', element.attr('id'));
  // You can extract more fields here if needed.
}

// Make each row selectable + hover effects
function makeSelectable() {
  $('.selectable')
    .off('click')
    .on('click', function () {
      $('.selectable').removeClass('selected');
      $(this).addClass('selected');
      // OnItemSelected($(this)); // uncomment if you want to persist selection
    });

  $('.selectable')
    .off('mouseover')
    .on('mouseover', function () {
      $(this).addClass('hover');
    });

  $('.selectable')
    .off('mouseleave')
    .on('mouseleave', function () {
      $(this).removeClass('hover');
    });

  // Restore previous selection
  const selectedJobId = sessionStorage.getItem('selected_job');
  if (selectedJobId) {
    $('.selectable')
      .filter((_, e) => e.id == selectedJobId)
      .addClass('selected');
  }
}


/**
 * Updates the table displaying the cluster's partitions and resource summary.
 * * @param {Array<Object>} resources - The list of resource/partition dictionaries returned by the backend.
 */
function updateResourcesTable(resources) {
  // Get the table body element using the recommended ID
  const resourcesTbody = document.getElementById('resources'); 
  
  if (!resourcesTbody) {
    console.error("Table body element not found with ID 'resources-table-body'.");
    return;
  }

  // Clear previous content
  resourcesTbody.innerHTML = ''; 

  // Iterate over each partition/resource object
  (resources || []).forEach(function (resource) {
    const row = document.createElement('tr');
    // Add classes for styling and interactivity
    row.className = 'selectable hover:bg-gray-50 dark:hover:bg-gray-700'; 
    
    // Determine the color class based on partition state (optional visual cue)
    let stateColor = 'text-gray-900 dark:text-gray-200';
    if (resource.available === 'down') {
        // Highlight critical state (e.g., partition DOWN)
        stateColor = 'text-red-600 dark:text-red-400 font-semibold';
    } else if (resource.state === 'INACTIVE') {
        // Highlight inactive/draining state
        stateColor = 'text-yellow-600 dark:text-yellow-400';
    }
    
    // Fill the columns with the new resource/partition data keys
    row.innerHTML = `
      <td class="border-bottom w-12 py-3.5 pr-3 text-left text-sm text-gray-900 dark:text-gray-200 sm:pl-6 lg:pl-8">
        ${resource.partition}
      </td>
      <td class="border-bottom px-3 py-3.5 text-left text-sm ${stateColor}">
        ${resource.state}
      </td>
      <td class="border-bottom px-3 py-3.5 text-left text-sm text-gray-900 dark:text-gray-200">
         ${resource.nodeslist} 
      </td>
      <td class="border-bottom px-3 py-3.5 text-left text-sm text-gray-900 dark:text-gray-200">
        ${resource.cpus} 
      </td>
      <td class="border-bottom px-3 py-3.5 text-left text-sm text-gray-900 dark:text-gray-200">
        ${resource.memory} MB 
      </td>
    `;
    
    resourcesTbody.appendChild(row);
  });
  
  makeSelectable(); 
}

// Render resources table (kept function name to avoid breaking references)
// function updateJobsTable(jobs) {
//   const jobsTbody = document.getElementById('resources');
//   if (!jobsTbody) return;

//   jobsTbody.innerHTML = '';
//   (jobs || []).forEach(function (job) {
//     const row = document.createElement('tr');
//     row.className = 'selectable';
//     row.id = job.job_id;

//     //row.innerHTML = `
//     //  <td class="border-bottom w-12 py-3.5 pr-3 text-left text-sm text-gray-900 sm:pl-6 lg:pl-8">${job.partition}</td>
//     //  <td class="border-bottom px-3 py-3.5 text-left text-sm text-gray-900">${job.available}</td>
//     //  <td class="border-bottom px-3 py-3.5 text-left text-sm text-gray-900">${job.timelimit}</td>
//     //  <td class="border-bottom px-3 py-3.5 text-left text-sm text-gray-900">${job.state}</td>
//     //  <td class="border-bottom px-3 py-3.5 text-left text-sm text-gray-900">${job.memory}MB</td>
//     //  <td class="border-bottom px-3 py-3.5 text-left text-sm text-gray-900">${job.cpus}</td>
//     //  <td class="border-bottom px-3 py-3.5 text-left text-sm text-gray-900">${job.nodeslist}</td>
//     //`;
//     row.innerHTML = `
//     <td class="border-bottom w-12 py-3.5 pr-3 text-left text-sm **text-gray-900 dark:text-gray-200** sm:pl-6 lg:pl-8">${job.partition}</td>
//     <td class="border-bottom px-3 py-3.5 text-left text-sm **text-gray-900 dark:text-gray-200**">${job.state}</td>
//     <td class="border-bottom px-3 py-3.5 text-left text-sm **text-gray-900 dark:text-gray-200**">${job.memory}MB</td>
//     <td class="border-bottom px-3 py-3.5 text-left text-sm **text-gray-900 dark:text-gray-200**">${job.cpus}</td>
//     <td class="border-bottom px-3 py-3.5 text-left text-sm **text-gray-900 dark:text-gray-200**">${job.nodeslist}</td>
//     `;
//     jobsTbody.appendChild(row);
//   });

//   makeSelectable();
// }


