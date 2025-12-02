function notificationsComponent() {
    return {
        open: false,
        count: 0,
        notifications: [],
	STORAGE_KEY: 'slurm_notifications',
        nextClientId: 0, 

        init() {
            this.loadNotifications();
            
            if (window.socket) {
                window.socket.on('new_job_notification', (data) => {
		    console.log("data 0", data);
                    this.addNotification(data);
                });
            }
        },

        toggleMenu() {
            this.open = !this.open;
            if (this.open) {
                this.count = 0;
                this.saveNotifications();
            }
        },

        addNotification(data) {
            const id = Date.now();
            let title = '';
            let message = '';

            const uniqueId = data.id || (Date.now() + '-' + this.nextClientId++);

            if (data.type === 'FAILED') {
                title = `Job ${data.job_name || data.job_id} Failed`;
                message = `Job ${data.job_id} finished with status FAILED.`;
            } else if (data.type === 'CANCELLED') {
                title = `Job ${data.job_name || data.job_id} Cancelled`;
                message = `Job ${data.job_id} was cancelled.`;
            } else if (data.type === 'TIMEOUT') {
                title = `Job ${data.job_name || data.job_id} Timeout`;
                message = `Job ${data.job_id} exceeded time limit.`;
            } else if (data.type === 'COMPLETED') {
                title = `Job ${data.job_name || data.job_id} Completed`;
                message = `Job ${data.job_id} finished successfully.`;
            } else if (data.type === 'MAINTENANCE') {
                title = `MAINTENANCE ALERT`;
                message = data.message || `Cluster maintenance is scheduled soon.`;
            } else {
                return;
            }

            const newNotification = {
                id: uniqueId,
                title: title,
                message: message,
                job_id: data.job_id,
                type: data.type,
                timestamp: data.timestamp || new Date().toISOString(),
                read: false
            };

            this.notifications.unshift(newNotification);
            this.count++;

            // Limit to  50 notifications
            if (this.notifications.length > 50) {
                this.notifications = this.notifications.slice(0, 50);
            }

            // Save in  localStorage
            this.saveNotifications();

            // Sonor notification
            //this.playNotificationSound(data.type);

            // navigator Notification
            //this.showBrowserNotification(title, message);
        },

	// view logs 
	viewJobLogs(jobId) {
    	    if (typeof window.JOB_DETAIL_URL_TEMPLATE === 'undefined') {
       		 console.error("JOB_DETAIL_URL_TEMPLATE is not defined globaly.");
        	return; 
   	    }
    	   const detailUrl = window.JOB_DETAIL_URL_TEMPLATE.replace('0', jobId);
    	   window.location.href = detailUrl;
	},

        markAllAsRead() {
            this.notifications.forEach(n => n.read = true);
            this.count = 0;
            this.saveNotifications();
        },

        clearAll() {
            if (confirm('Clear all notifications?')) {
                this.notifications = [];
                this.count = 0;
                this.saveNotifications();
            }
        },

        saveNotifications() {
            try {
                localStorage.setItem('slurm_notifications', JSON.stringify(this.notifications));
            } catch (e) {
                console.error('Failed to save notifications:', e);
            }
        },

        loadNotifications() {
            try {
                //const saved = localStorage.getItem('slurm_notifications')
		const saved = localStorage.getItem(this.STORAGE_KEY);;
                if (saved) {
                    this.notifications = JSON.parse(saved);
                    this.count = this.notifications.filter(n => !n.read).length;
		    const maxId = this.notifications.reduce((max, n) => Math.max(max, parseInt(n.id) || 0), 0);
                    this.nextClientId = maxId + 1;
                }
            } catch (e) {
                console.error('Failed to load notifications:', e);
            }
        },

        /*playNotificationSound(type) {
            if (type === 'FAILED' || type === 'TIMEOUT') {
                // play error sonor
                // new Audio('/static/sounds/error.mp3').play().catch(() => {});
            }
        },

        showBrowserNotification(title, message) {
            if ('Notification' in window && Notification.permission === 'granted') {
                new Notification(title, {
                    body: message,
                    icon: '/static/img/slurm-icon.png',
                    badge: '/static/img/slurm-badge.png'
                });
            } else if ('Notification' in window && Notification.permission !== 'denied') {
                Notification.requestPermission().then(permission => {
                    if (permission === 'granted') {
                        new Notification(title, {
                            body: message,
                            icon: '/static/img/slurm-icon.png'
                        });
                    }
                });
            }
        }*/
    };
}

