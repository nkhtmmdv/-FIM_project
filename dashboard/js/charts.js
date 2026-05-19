/**
 * Chart rendering for the FIM dashboard.
 * Uses Chart.js v4 with dark-themed styling.
 */

let timelineChart = null;

/**
 * Render or update the 24-hour alert timeline chart.
 * @param {Array<{hour: string, alerts: number}>} rows - Hourly alert counts from API.
 */
function renderTimeline(rows) {
    const canvas = document.getElementById('timeline');
    if (!canvas) return;

    const labels = (rows || []).map(function (r) {
        const d = new Date(r.hour);
        return d.getHours().toString().padStart(2, '0') + ':00';
    });
    const data = (rows || []).map(function (r) { return r.alerts; });

    const chartData = {
        labels: labels,
        datasets: [{
            label: 'Alerts',
            data: data,
            borderColor: '#60a5fa',
            backgroundColor: 'rgba(96,165,250,.15)',
            fill: true,
            tension: 0.35,
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: '#60a5fa',
            pointHoverRadius: 6
        }]
    };

    const chartOptions = {
        responsive: true,
        maintainAspectRatio: true,
        interaction: { mode: 'index', intersect: false },
        plugins: {
            legend: { labels: { color: '#e7edf7', font: { family: 'Inter', size: 12 } } },
            tooltip: {
                backgroundColor: '#0f172a',
                titleColor: '#e7edf7',
                bodyColor: '#9aa4b2',
                borderColor: '#25324d',
                borderWidth: 1,
                padding: 10,
                cornerRadius: 8
            }
        },
        scales: {
            x: {
                grid: { color: 'rgba(37,50,77,.4)', drawBorder: false },
                ticks: { color: '#9aa4b2', font: { size: 11 } }
            },
            y: {
                beginAtZero: true,
                grid: { color: 'rgba(37,50,77,.4)', drawBorder: false },
                ticks: { color: '#9aa4b2', font: { size: 11 }, stepSize: 1 }
            }
        }
    };

    if (timelineChart) {
        timelineChart.data = chartData;
        timelineChart.update();
    } else {
        timelineChart = new Chart(canvas, {
            type: 'line',
            data: chartData,
            options: chartOptions
        });
    }
}
