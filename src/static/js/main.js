$(document).ready(function() {
    if (typeof window.socket !== 'undefined') {

        window.socket.on('stats', function(stats) {
            console.log('Received update:', stats);
            if (stats.error) {
                console.error('Error received:', stats.error);
            } else {
                for (const [key, value] of Object.entries(stats.html)) {
                    $('#' + key).html(value);
                }
            }   
        });
        setInterval(() => {
            window.socket.emit('request_jobs');
        },  180000);

    } else {
        console.error('Socket.io is not initialized.');
    }
        
});
