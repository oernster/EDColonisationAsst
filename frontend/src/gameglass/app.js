document.addEventListener('DOMContentLoaded', () => {
    const inProgressList = document.getElementById('in-progress-list');
    const completedList = document.getElementById('completed-list');
    // Must match DEFAULT_BACKEND_PORT in backend/src/utils/ports.py.
    const API_URL = 'http://127.0.0.1:47021/api/sites';

    const fetchData = async () => {
        try {
            const response = await fetch(API_URL);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            updateUI(data);
        } catch (error) {
            console.error('Error fetching data:', error);
            inProgressList.innerHTML = '<p>Error loading data. Is the backend running?</p>';
        }
    };

    const updateUI = (data) => {
        // Clear existing content
        inProgressList.innerHTML = '';
        completedList.innerHTML = '';

        // Populate In-Progress Sites
        if (data.in_progress_sites && data.in_progress_sites.length > 0) {
            data.in_progress_sites.forEach(site => {
                const siteDiv = document.createElement('div');
                siteDiv.className = 'site';

                const siteName = document.createElement('div');
                siteName.className = 'site-name';
                siteName.textContent = `${site.station_name} (${site.system_name})`;
                siteDiv.appendChild(siteName);

                const commoditiesList = document.createElement('ul');
                commoditiesList.className = 'commodities-list';

                site.commodities.forEach(commodity => {
                    if (commodity.remaining_amount > 0) {
                        const commodityItem = document.createElement('li');
                        commodityItem.className = 'commodity';
                        commodityItem.innerHTML = `
                            <span class="commodity-name">${commodity.name_localised}</span>
                            <span class="commodity-amount">${commodity.provided_amount} / ${commodity.required_amount}</span>
                        `;
                        commoditiesList.appendChild(commodityItem);
                    }
                });

                siteDiv.appendChild(commoditiesList);
                inProgressList.appendChild(siteDiv);
            });
        } else {
            inProgressList.innerHTML = '<p>No sites currently under construction.</p>';
        }

        // Populate Completed Sites
        if (data.completed_sites && data.completed_sites.length > 0) {
            data.completed_sites.forEach(site => {
                const siteDiv = document.createElement('div');
                siteDiv.className = 'site';
                siteDiv.textContent = `${site.station_name} (${site.system_name})`;
                completedList.appendChild(siteDiv);
            });
        } else {
            completedList.innerHTML = '<p>No completed sites found.</p>';
        }
    };

    fetchData();
    // Refresh data every 30 seconds
    setInterval(fetchData, 30000);
});