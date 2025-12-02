// Handles the job submission page for slurm_modular:
// - Prefills the form from localStorage
// - Listens to SocketIO "submit" updates
// - Shows a preview modal with full SBATCH script
// - Submits via WebSocket to slurm_modular API

let selected; // optional row/element selection state

$(function () {
  // 1) Show job form if present
  const jobForm = $('#job_form');
  if (jobForm.length > 0) {
    jobForm.css('display', 'block');
  } else {
    console.warn('Job form not found (#job_form)');
  }

  // 2) Socket listener for server-side updates
  if (window.socket) {
    window.socket
      .off('submit')
      .on('submit', function (msg) {
        console.log('Received submit update:', msg);
        if (msg && msg.html) {
          for (const [key, value] of Object.entries(msg.html)) {
            $('#' + key).html(value);
          }
        }
      });

    // Listen for job submission response
    window.socket
      .off('submit_result')
      .on('submit_result', function (response) {
        console.log('Job submission response:', response);
        const message = document.getElementById('message');
        
        if (response.success) {
          message.textContent = `Job submitted successfully! Job ID: ${response.job_id}`;
          message.className = 'message success';
          message.style.display = 'block';
          
          // Clear form after successful submission (optional)
          // document.getElementById('job_form').reset();
          // clearFormData();
        } else {
          message.textContent = `Error submitting job: ${response.error || response.message || 'Unknown error'}`;
          message.className = 'message error';
          message.style.display = 'block';
        }
        
        // Hide message after 5 seconds
        setTimeout(() => {
          message.style.display = 'none';
        }, 5000);
      });
    
    // Listen for job_submitted broadcast (when any user submits)
    window.socket
      .off('job_submitted')
      .on('job_submitted', function (data) {
        console.log('New job submitted:', data);
        // Optionally refresh job list or show notification
      });
  }

  // 3) Modal close buttons / outside click
  const closeEl = document.querySelector('.close');
  if (closeEl) closeEl.onclick = closeModal;

  window.addEventListener('click', function (event) {
    const modal = document.getElementById('previewModal');
    if (modal && event.target === modal) {
      closeModal();
    }
  });
});

// ------------------------------
// LocalStorage Form Persistence
// ------------------------------
document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('job_form');

  if (form) {
    const STORAGE_KEY = 'slurm_submit_form_data';

    // Load saved data from localStorage and pre-fill the form
    function loadFormData() {
      const savedData = localStorage.getItem(STORAGE_KEY);
      if (savedData) {
        try {
          const data = JSON.parse(savedData);
          
          for (const [name, value] of Object.entries(data)) {
            const field = form.elements[name];
            if (field) {
              // Handle checkboxes
              if (field.type === 'checkbox') {
                field.checked = (value === 'on' || value === 'true');
              } else {
                // Handle inputs and selects
                field.value = value;
              }
            }
          }
        } catch (e) {
          console.error("Error loading data from localStorage:", e);
          localStorage.removeItem(STORAGE_KEY);
        }
      }
    }

    // Save all form name/value pairs to localStorage
    function saveFormData() {
      const data = {};
      new FormData(form).forEach((value, key) => {
        data[key] = value;
      });
      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    }
    
    // Initialization
    loadFormData();

    // Save on every form change
    form.addEventListener('input', saveFormData);

    // Function to manually clear data
    window.clearFormData = function() {
      localStorage.removeItem(STORAGE_KEY);
      console.log("Form data cleared from localStorage.");
    };
  }
});

// ------------------------------
// Build SBATCH Script from Form
// ------------------------------
function buildSbatchScriptFromForm() {
  const name    = (document.querySelector('input[name="name"]')?.value || '').trim();
  const account = (document.querySelector('input[name="account"]')?.value || '').trim();
  const part    = (document.querySelector('select[name="partition"]')?.value || 'standard').trim();
  const ntasks  = (document.querySelector('input[name="ntasks"]')?.value || '1').trim();
  const qos     = (document.querySelector('select[name="qos"]')?.value || 'normal').trim();
  const tlimit  = (document.querySelector('input[name="time"]')?.value || '60').trim();
  const cmd     = (document.querySelector('textarea[name="job_script"]')?.value || '').trim();

  // If user already wrote SBATCH lines in Command, show as-is
  const hasSBATCH = cmd.split('\n').some(line => line.trim().startsWith('#SBATCH'));
  if (hasSBATCH) {
    return cmd.startsWith('#!') ? cmd : `#!/bin/bash\n${cmd}`;
  }

  // Otherwise compose a clean SBATCH header
  const lines = ['#!/bin/bash', '# ---- Generated SBATCH Script ----'];
  if (name)    lines.push(`#SBATCH -J ${name}`);
  if (account) lines.push(`#SBATCH --account=${account}`);
  if (part)    lines.push(`#SBATCH --partition=${part}`);
  if (tlimit)  lines.push(`#SBATCH --time=${tlimit}`);
  if (ntasks)  lines.push(`#SBATCH --ntasks=${ntasks}`);
  if (qos)     lines.push(`#SBATCH --qos=${qos}`);
  lines.push('# ---------------------------------');
  lines.push(cmd || 'echo "Hello HPC!"');

  return lines.join('\n');
}

// ------------------------------
// Submit Job via WebSocket
// ------------------------------
document.addEventListener('DOMContentLoaded', function() {
  const form = document.getElementById('job_form');
  
  if (!form) return;

  form.addEventListener('submit', function(e) {
    e.preventDefault();
    
    if (!window.socket) {
      console.error('WebSocket not connected');
      const message = document.getElementById('message');
      message.textContent = 'Error: WebSocket not connected';
      message.className = 'message error';
      message.style.display = 'block';
      return;
    }

    // Gather form data
    const formData = new FormData(form);
    
    // Get username (from current_user or session)
    const username = window.currentUsername || formData.get('username') || 'unknown';
    
    // Get form values
    const jobName = formData.get('name') || 'unnamed_job';
    const account = formData.get('account') || '';
    const partition = formData.get('partition') || 'normal';
    const qos = formData.get('qos') || 'normal';
    const ntasks = parseInt(formData.get('ntasks') || '1');
    const timeLimit = parseInt(formData.get('time') || '60');
    const workdir = formData.get('workdir') || `/scratch/${username}`;
    
    // Get the user script (textarea content)
    const userScript = formData.get('job_script') || 'echo "Hello HPC!"';
    
    // Build output/error paths
    const outputLoc = formData.get('output') || `/scratch/${username}/${jobName}-%j.out`;
    const errorLoc = formData.get('error') || `/scratch/${username}/${jobName}-%j.err`;

    // Build payload matching exact API format
    const payload = {
      script: "#!/bin/bash\n" + userScript + "\n",
      job: {
        name: jobName,
        account: account,
        partition: partition,
        qos: qos,
        ntasks: ntasks,
        time_limit: {
          set: true,
          number: timeLimit
        },
        current_working_directory: workdir,
        standard_output: outputLoc,
        standard_error: errorLoc,
        environment: [
          "PATH=/usr/local/bin:/usr/bin:/bin"
        ]
      }
    };

    // Build complete submission data with username
    const jobData = {
      name: jobName,
      script: payload.script,
      username: username,
      payload: payload,  // Complete payload for API
      job: payload.job   // Job options for backward compatibility
    };

    console.log('Submitting job:', jobData);

    // Emit via WebSocket
    window.socket.emit('submit_job', jobData);

    // Show loading message
    const message = document.getElementById('message');
    message.textContent = 'Submitting job...';
    message.className = 'message info';
    message.style.display = 'block';
  });
});

// ------------------------------
// Preview Job Script
// ------------------------------
function previewJobForm() {
  const script = buildSbatchScriptFromForm();

  const previewEl = document.getElementById('previewContent');
  if (previewEl) {
    previewEl.innerHTML = `<pre style="white-space:pre-wrap;margin:0;">${escapeHtml(script)}</pre>`;
  }

  openModal();
}

// HTML escaper
function escapeHtml(s) {
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;');
}

// ------------------------------
// Modal Controls
// ------------------------------
function openModal() {
  const modal = document.getElementById('previewModal');
  if (modal) modal.style.display = 'block';
}

function closeModal() {
  const modal = document.getElementById('previewModal');
  if (modal) modal.style.display = 'none';
}

// ------------------------------
// Selection Helpers
// ------------------------------
function OnItemSelected(element) {
  selected = element;
  sessionStorage.setItem('selected_job', element[0].id);
  $('.selectable').removeClass('selected');
  element.addClass('selected');
}

function makeSelectable() {
  $('.selectable').off('click').on('click', function () {
    $(this).toggleClass('selected');
    OnItemSelected($(this));
  });

  $('.selectable').off('mouseover').on('mouseover', function () {
    $(this).addClass('hover');
  });

  $('.selectable').off('mouseleave').on('mouseleave', function () {
    $(this).removeClass('hover');
  });

  $('.selectable')
    .filter((_, e) => e.id == sessionStorage.getItem('selected_job'))
    .addClass('selected');
}

// ------------------------------
// Auto-fill Time on QOS Change
// ------------------------------
function OnQosChanged(selectEl) {
  const opt = selectEl.options[selectEl.selectedIndex];
  const minutes = opt.getAttribute('data-default-time');
  if (minutes) {
    const timeInput = document.getElementById('time_input');
    if (timeInput) {
      timeInput.value = minutes;
    }
  }
}

// ------------------------------
// Set Default Values on Load
// ------------------------------
document.addEventListener('DOMContentLoaded', () => {
  const qosInput = document.getElementById('qos_input'); 
  const partitionInput = document.getElementById('partition_input');

  if (qosInput && typeof window.getDefaultQos === 'function') {
    const defaultQos = window.getDefaultQos();
    if (defaultQos) {
      qosInput.value = defaultQos;
      console.log(`Default QOS applied: ${defaultQos}`);
    }
  }

  if (partitionInput && typeof window.getDefaultPartition === 'function') {
    const defaultPartition = window.getDefaultPartition();
    if (defaultPartition) {
      partitionInput.value = defaultPartition;
      console.log(`Default partition applied: ${defaultPartition}`);
    }
  }
});

// ------------------------------
// Expose Functions Globally
// ------------------------------
window.previewJobForm = previewJobForm;
window.OnQosChanged = OnQosChanged;
window.closeModal = closeModal;