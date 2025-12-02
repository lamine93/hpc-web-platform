$(document).ready(function() {});

const refreshRateSelect = document.getElementById('refresh-rate');
const defaultQosSelect = document.getElementById('default-qos');
const defaultPartitionSelect = document.getElementById('default-partition');


// Function to load saved refresh rate from LocalStorage

function loadRefreshRate() {
  const savedRate = localStorage.getItem('refreshRate');
  if (savedRate) {
     refreshRateSelect.value = savedRate;
  } else {
    // Set default value if none is saved (60s)
    refreshRateSelect.value = "60";
    localStorage.setItem('refreshRate', "60");
   }
}

function loadDefaultSlurmSettings() {
    const savedQos = localStorage.getItem('defaultQos');
     
    if (savedQos) {
        defaultQosSelect.value = savedQos;
    }

    const savedPartition = localStorage.getItem('defaultPartition');
    if (savedPartition) {
        defaultPartitionSelect.value = savedPartition;
    }
}

window.saveRefreshRate = function() {
    const newRateString = refreshRateSelect.value;
    localStorage.setItem('refreshRate', newRateString);

    if (typeof window.startJobsPolling === 'function') {
        window.startJobsPolling();
    }
}

window.saveDefaultSlurmSettings = function() {
    localStorage.setItem('defaultQos', defaultQosSelect.value);
    localStorage.setItem('defaultPartition', defaultPartitionSelect.value);
     
}

loadRefreshRate();
loadDefaultSlurmSettings();

