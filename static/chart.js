const energyChart = new Chart(ctx, {
    type: 'line', // Best for showing trends over time
    data: {
        labels: ['00:00', '04:00', '08:00', '12:00', '16:00', '20:00'], // X-axis (Time)
        datasets: [{
            label: 'Energy Consumption (kWh)',
            data: [0.5, 0.4, 1.2, 2.5, 1.8, 3.0], // Y-axis (Your IoT data)
            backgroundColor: 'rgba(75, 192, 192, 0.2)', // Fill color
            borderColor: 'rgba(75, 192, 192, 1)',     // Line color
            borderWidth: 2,
            tension: 0.3 // Makes the line slightly curved
        }]
    },
    options: {
        responsive: true,
        scales: {
            y: {
                beginAtZero: true,
                title: {
                    display: true,
                    text: 'Kilowatts (kWh)'
                }
            },
            x: {
                title: {
                    display: true,
                    text: 'Time of Day'
                }
            }
        }
    }
});