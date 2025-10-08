// static/dashboard.js

function initDashboardCharts(data) {
    const chartInstances = {};

    // Globale Chart Optionen für den Dark-Mode
    const commonOptions = {
        chart: { foreColor: '#adb5bd', toolbar: { show: false } },
        grid: { borderColor: '#495057' },
        xaxis: { labels: { style: { colors: '#adb5bd' } }, axisBorder: { color: '#495057' }, axisTicks: { color: '#495057' } },
        yaxis: { labels: { style: { colors: '#adb5bd' } } },
        tooltip: { theme: 'dark' }
    };
    const donutOptions = { ...commonOptions, chart: { ...commonOptions.chart, type: 'donut', height: 350 }, legend: { position: 'bottom' }, dataLabels: { enabled: true, formatter: (val) => `${val.toFixed(1)}%` } };
    const barOptions = { ...commonOptions, chart: { ...commonOptions.chart, type: 'bar', height: 350 }, plotOptions: { bar: { borderRadius: 4, horizontal: true } }, dataLabels: { enabled: false } };
    const verticalBarOptions = { ...barOptions, plotOptions: { bar: { borderRadius: 4, horizontal: false } } };

    // --- Chart Definitionen ---
    const chartDefinitions = {
        '#uptime-chart': {
            options: { ...commonOptions, series: [], chart: { ...commonOptions.chart, type: 'bar', height: 350, stacked: true }, plotOptions: { bar: { horizontal: true } }, stroke: { width: 1, colors: ['#343a40'] }, xaxis: { ...commonOptions.xaxis, categories: [], title: { text: 'Stunden' } }, legend: { position: 'top', horizontalAlign: 'left' }, tooltip: { y: { formatter: (val) => `${val} Std` } } },
            init: (chartData) => {
                const printerNames = Object.keys(chartData);
                if (printerNames.length === 0) return null;
                return {
                    series: [
                        { name: 'Drucken', data: printerNames.map(p => chartData[p].PRINTING.toFixed(1)) },
                        { name: 'Leerlauf', data: printerNames.map(p => chartData[p].IDLE.toFixed(1)) },
                        { name: 'Wartung', data: printerNames.map(p => chartData[p].MAINTENANCE.toFixed(1)) },
                        { name: 'Offline/Fehler', data: printerNames.map(p => ((chartData[p].OFFLINE || 0) + (chartData[p].ERROR || 0)).toFixed(1)) },
                    ],
                    xaxis: { categories: printerNames }
                };
            },
            dataKey: 'uptime_chart_data'
        },
        '#production-trend-chart': {
            options: { ...commonOptions, chart: {...commonOptions.chart, type: 'line', height: 350}, series: [], colors: ['#20c997', '#dc3545'], xaxis: {...commonOptions.xaxis, categories: []}, stroke: { curve: 'smooth', width: 2 }, legend: { position: 'top' }, yaxis: { labels: { formatter: (val) => val.toFixed(0) } } },
            init: (d) => ({ series: [{ name: 'Erfolgreich', data: d.successful }, { name: 'Fehlgeschlagen', data: d.failed }], xaxis: { categories: d.labels } }),
            dataKey: 'production_trend_chart'
        },
        '#jobs-by-weekday-chart': {
            options: { ...verticalBarOptions, series: [], xaxis: {...verticalBarOptions.xaxis, categories: [] }, yaxis: { labels: { formatter: (val) => val.toFixed(0) } } },
            init: (d) => ({ series: [{ name: 'Abgeschlossene Aufträge', data: d.data }], xaxis: { categories: d.labels } }),
            dataKey: 'jobs_by_weekday_chart'
        },
        '#material-trend-chart': {
            options: { ...commonOptions, series: [], chart: { ...commonOptions.chart, type: 'area', height: 350 }, dataLabels: { enabled: false }, stroke: { curve: 'smooth' }, xaxis: { ...commonOptions.xaxis, type: 'category', categories: [] } },
            init: (d) => ({ series: [{ name: 'Verbrauch (g)', data: d.data }], xaxis: { categories: d.labels } }),
            dataKey: 'material_trend_chart'
        },
        '#avg-job-times-chart': {
            options: { ...verticalBarOptions, series: [], tooltip: { y: { formatter: (val) => `${val} min` } } },
            init: (d) => ({ series: [{ name: 'Minuten', data: d.data }], xaxis: { categories: d.labels } }),
            dataKey: 'avg_job_times_chart'
        },
        '#maintenance-by-type-chart': {
            options: { ...donutOptions, chart: {...donutOptions.chart, type: 'pie'}, series: [], labels: [], dataLabels: { enabled: true, formatter: (val, opts) => opts.w.config.series[opts.seriesIndex] }, tooltip: { y: { formatter: (val) => `${val}x durchgeführt` } } },
            init: (d) => ({ series: d.data, labels: d.labels }),
            dataKey: 'maintenance_by_type_chart'
        },
        '#print-hours-printer-chart': {
            options: { ...verticalBarOptions, series: [], tooltip: { y: { formatter: (val) => `${val}h` } } },
            init: (d) => ({ series: [{ name: 'Druckstunden', data: d.data }], xaxis: { categories: d.labels } }),
            dataKey: 'print_hours_per_printer_chart'
        },
        '#costs-per-printer-chart': {
            options: { ...verticalBarOptions, series: [], tooltip: { y: { formatter: (val) => `${val.toFixed(2)} €` } } },
            init: (d) => ({ series: [{ name: 'Gesamtkosten', data: d.data }], xaxis: { categories: d.labels } }),
            dataKey: 'costs_per_printer_chart'
        },
        '#stock-by-material-chart': {
            options: { ...donutOptions, series: [], labels: [], tooltip: { y: { formatter: (val) => `${val.toFixed(2)} kg` } } },
            init: (d) => ({ series: d.data, labels: d.labels }),
            dataKey: 'stock_by_material_chart'
        },
        '#material-consumption-chart': {
            options: { ...donutOptions, series: [], labels: [], colors: [], tooltip: { y: { formatter: (val) => `${val.toFixed(2)} kg` } } },
            init: (d) => ({ series: d.data, labels: d.labels, colors: d.colors }),
            dataKey: 'material_consumption_chart'
        },
        '#top-filaments-chart': {
            options: { ...barOptions, series: [], tooltip: { y: { title: { formatter: () => 'Aufträge' } } } },
            init: (d) => ({ series: [{ name: 'Anzahl Aufträge', data: d.data }], xaxis: { categories: d.labels } }),
            dataKey: 'top_filaments_chart'
        },
        '#success-rate-material-chart': {
            options: { ...verticalBarOptions, series: [], yaxis: { ...verticalBarOptions.yaxis, max: 100, labels: { formatter: (val) => `${val}%`} }, tooltip: { y: { formatter: (val) => `${val}%` } } },
            init: (d) => ({ series: [{ name: 'Erfolgsrate', data: d.data }], xaxis: { categories: d.labels } }),
            dataKey: 'success_rate_material_chart'
        },
        '#failures-by-material-chart': {
            options: { ...donutOptions, series: [], labels: [], dataLabels: { enabled: true, formatter: (val, opts) => opts.w.config.series[opts.seriesIndex] }, tooltip: { y: { formatter: (val) => `${val} Fehldruck(e)` } } },
            init: (d) => ({ series: d.data, labels: d.labels }),
            dataKey: 'failures_by_material_chart'
        },
        '#material-efficiency-chart': {
            options: { ...donutOptions, chart: {...donutOptions.chart, type: 'pie' }, series: [], labels: [], colors: ['#20c997', '#dc3545'], tooltip: { y: { formatter: (val) => `${val.toFixed(0)} g` } } },
            init: (d) => ({ series: d.data, labels: d.labels }),
            dataKey: 'material_efficiency_chart'
        },
        // NEUE PERFORMANCE CHARTS
        '#oee-components-chart': {
            options: { 
                ...commonOptions, 
                chart: { ...commonOptions.chart, type: 'radar', height: 350 }, 
                series: [], 
                xaxis: { categories: [] },
                yaxis: { max: 100, labels: { formatter: (val) => `${val}%` } },
                plotOptions: { radar: { polygons: { strokeColors: '#495057', fill: { colors: ['rgba(13, 110, 253, 0.05)', 'rgba(13, 110, 253, 0.1)'] } } } }
            },
            init: (d) => ({ 
                series: [{ name: 'Wert', data: d.data }], 
                xaxis: { categories: d.labels } 
            }),
            dataKey: 'oee_components_chart'
        },
        '#capacity-chart': {
            options: { 
                ...commonOptions, 
                chart: { ...commonOptions.chart, type: 'area', height: 350 }, 
                series: [], 
                colors: ['#0d6efd'],
                stroke: { curve: 'smooth', width: 2 },
                fill: { type: 'gradient', gradient: { shadeIntensity: 1, opacityFrom: 0.7, opacityTo: 0.2 } },
                xaxis: { ...commonOptions.xaxis, categories: [] },
                yaxis: { max: 100, labels: { formatter: (val) => `${val}%` } }
            },
            init: (d) => ({ 
                series: [{ name: 'Auslastung', data: d.data }], 
                xaxis: { categories: d.labels } 
            }),
            dataKey: 'capacity_chart'
        },
        '#lead-time-chart': {
            options: { 
                ...verticalBarOptions, 
                series: [], 
                colors: ['#20c997'],
                tooltip: { y: { formatter: (val) => `${val}h` } },
                plotOptions: { bar: { distributed: true } },
                legend: { show: false }
            },
            init: (d) => ({ 
                series: [{ name: 'Durchlaufzeit', data: d.data }], 
                xaxis: { categories: d.labels } 
            }),
            dataKey: 'lead_time_chart'
        },
        // NEUE KOSTEN/ROI CHARTS
        '#cost-breakdown-chart': {
            options: { 
                ...donutOptions, 
                series: [], 
                labels: [],
                colors: ['#fd7e14', '#6f42c1', '#0dcaf0'],
                tooltip: { y: { formatter: (val) => `${val.toFixed(2)} €` } }
            },
            init: (d) => ({ series: d.data, labels: d.labels }),
            dataKey: 'cost_breakdown_chart'
        },
        '#monthly-costs-chart': {
            options: { 
                ...commonOptions, 
                chart: { ...commonOptions.chart, type: 'line', height: 350 }, 
                series: [],
                colors: ['#dc3545'],
                stroke: { curve: 'smooth', width: 3 },
                xaxis: { ...commonOptions.xaxis, categories: [] },
                tooltip: { y: { formatter: (val) => `${val.toFixed(2)} €` } }
            },
            init: (d) => ({ 
                series: [{ name: 'Kosten', data: d.data }], 
                xaxis: { categories: d.labels } 
            }),
            dataKey: 'monthly_costs_chart'
        },
        '#roi-chart': {
            options: { 
                ...verticalBarOptions, 
                series: [],
                colors: ['#20c997', '#dc3545'],
                plotOptions: { 
                    bar: { 
                        distributed: true,
                        dataLabels: { position: 'top' }
                    } 
                },
                dataLabels: { 
                    enabled: true, 
                    formatter: (val) => `${val.toFixed(1)}%`,
                    offsetY: -20,
                    style: { fontSize: '12px', colors: ['#adb5bd'] }
                },
                tooltip: { y: { formatter: (val) => `${val.toFixed(1)}%` } }
            },
            init: (d) => ({ 
                series: [{ name: 'ROI', data: d.data }], 
                xaxis: { categories: d.labels } 
            }),
            dataKey: 'roi_chart'
        },
        '#energy-costs-chart': {
            options: { 
                ...barOptions, 
                series: [],
                colors: ['#ffc107'],
                tooltip: { y: { formatter: (val) => `${val.toFixed(2)} €` } }
            },
            init: (d) => ({ 
                series: [{ name: 'Energiekosten', data: d.data }], 
                xaxis: { categories: d.labels } 
            }),
            dataKey: 'energy_costs_chart'
        },
        '#maintenance-vs-production-chart': {
            options: { 
                ...donutOptions,
                chart: { ...donutOptions.chart, type: 'pie' },
                series: [], 
                labels: [],
                colors: ['#0d6efd', '#ffc107'],
                tooltip: { y: { formatter: (val) => `${val.toFixed(2)} €` } }
            },
            init: (d) => ({ series: d.data, labels: d.labels }),
            dataKey: 'maintenance_vs_production_chart'
        }
    };
    
    function renderChart(selector) {
        const element = document.querySelector(selector);
        if (!element || element.hasAttribute('data-rendered')) return;

        const definition = chartDefinitions[selector];
        if (!definition) {
            console.warn(`No definition found for selector: ${selector}`);
            return;
        }

        const chartData = data[definition.dataKey];
        if (!chartData) {
            console.warn(`No data found for key: ${definition.dataKey}`);
            element.innerHTML = '<div class="text-center text-muted p-5">Keine Daten verfügbar.</div>';
            return;
        }

        // Prüfe ob Daten vorhanden sind, aber erllaube leere Arrays
        if (Array.isArray(chartData.data) && chartData.data.length === 0) {
            element.innerHTML = '<div class="text-center text-muted p-5">Keine Daten verfügbar.</div>';
            return;
        }

        // Spezialfall für production_trend_chart - hat successful/failed statt data
        if (definition.dataKey === 'production_trend_chart') {
            if (!chartData.successful || !chartData.failed || chartData.labels.length === 0) {
                element.innerHTML = '<div class="text-center text-muted p-5">Keine Produktionsdaten verfügbar.</div>';
                return;
            }
        }

        const update = definition.init(chartData);
        if (!update) {
            element.innerHTML = '<div class="text-center text-muted p-5">Keine Daten verfügbar.</div>';
            return;
        }

        try {
            const finalOptions = { ...definition.options };
            finalOptions.series = update.series;
            if (update.labels) finalOptions.labels = update.labels;
            if (update.colors) finalOptions.colors = update.colors;
            if (update.xaxis) finalOptions.xaxis = { ...finalOptions.xaxis, ...update.xaxis };

            const chart = new ApexCharts(element, finalOptions);
            chart.render();
            element.setAttribute('data-rendered', 'true');
            chartInstances[selector] = chart;
        } catch (error) {
            console.error(`Error rendering chart ${selector}:`, error);
            element.innerHTML = '<div class="text-center text-danger p-5">Fehler beim Laden des Charts.</div>';
        }
    }

    const tabs = document.querySelectorAll('#dashboardTabs button[data-bs-toggle="tab"]');
    tabs.forEach(tab => {
        tab.addEventListener('shown.bs.tab', event => {
            // Mehrere Versuche mit steigender Verzögerung
            const targetSelector = event.target.getAttribute('data-bs-target');
            
            const attemptRender = (attempt = 0) => {
                const pane = document.querySelector(targetSelector);
                
                if (!pane && attempt < 5) {
                    // Versuche es nochmal nach weiteren 50ms (max 5 Versuche)
                    setTimeout(() => attemptRender(attempt + 1), 50);
                    return;
                }
                
                if (!pane) {
                    console.error('Tab pane not found after multiple attempts:', targetSelector);
                    return;
                }
                
                const chartContainers = pane.querySelectorAll('.chart-container');
                if (chartContainers.length === 0) {
                    console.warn('No chart containers found in pane:', targetSelector);
                    return;
                }
                
                const selectors = Array.from(chartContainers)
                    .map(el => el.id ? `#${el.id}` : null)
                    .filter(id => id !== null && id !== '#');
                
                console.log(`Rendering ${selectors.length} charts in ${targetSelector}:`, selectors);
                selectors.forEach(renderChart);
            };
            
            attemptRender();
        });
    });

    // Initialisiere die Charts im ersten, standardmäßig aktiven Tab
    window.addEventListener('load', () => {
        setTimeout(() => {
            const activePane = document.querySelector('.tab-pane.active, .tab-pane.show.active');
            if (activePane) {
                const initialSelectors = Array.from(activePane.querySelectorAll('.chart-container'))
                    .map(el => el.id ? `#${el.id}` : null)
                    .filter(id => id !== null && id !== '#');
                console.log('Initial charts to render:', initialSelectors);
                initialSelectors.forEach(renderChart);
            } else {
                console.error('No active tab pane found on load');
            }
        }, 300);
    });
}