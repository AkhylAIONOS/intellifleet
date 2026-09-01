// import { useState } from 'react';
// import { useAppStore } from '../store/appStore';
// import './RouteDashboard.css';

// export const RouteDashboard = () => {
//     const { activeRoutes } = useAppStore();
//     const [currentIndex, setCurrentIndex] = useState(0);
//     const [isOpen, setIsOpen] = useState(false); // State to toggle dashboard visibility
//     // Convert activeRoutes object to array
//     const routesArray = Object.values(activeRoutes);

//     // Reset index if current route is removed
//     if (currentIndex >= routesArray.length && routesArray.length > 0) {
//         setCurrentIndex(0);
//     }

//     const handleNext = () => {
//         if (currentIndex < routesArray.length - 1) {
//             setCurrentIndex(currentIndex + 1);
//         }
//     };

//     const handlePrevious = () => {
//         if (currentIndex > 0) {
//             setCurrentIndex(currentIndex - 1);
//         }
//     };

//     // No routes state
//     if (routesArray.length === 0) {
//         return (
//             <div className="route-dashboard empty">
//                 <div className="dashboard-header">
//                     <h3>Routes</h3>
//                 </div>
//                 <div className="empty-state">
//                     <div className="empty-icon">🗺️</div>
//                     <p className="empty-message">No routes to show</p>
//                     <p className="empty-hint">Plan routes to see them here</p>
//                 </div>
//                 <div className="navigation-controls single-btn">
//                      <button className="close-button" onClick={toggleDashboard}>Close</button>
//                 </div>
//             </div>
//         );
//     }

//     const toggleDashboard = () => {
//         setIsOpen(!isOpen);
//     };

//     // 1. Minimized View (The Button)
//     if (!isOpen) {
//         return (
//             <div className="route-trigger-container">
//                 <button className="route-trigger-btn" onClick={toggleDashboard}>
//                     <span className="trigger-icon">🗺️</span>
//                     <span className="trigger-text">Routes</span>
//                     {routesArray.length > 0 && (
//                         <span className="trigger-badge">{routesArray.length}</span>
//                     )}
//                 </button>
//             </div>
//         );
//     }

//     // 2. Expanded View (The Card)
//     // No routes state (Inside Card)
//     if (routesArray.length === 0) {
//         return (
//             <div className="route-dashboard empty">
//                 <div className="dashboard-header">
//                     <h3>Routes</h3>
//                     <button className="close-icon-btn" onClick={toggleDashboard}>×</button>
//                 </div>
//                 <div className="empty-state">
//                     <div className="empty-icon">🗺️</div>
//                     <p className="empty-message">No routes to show</p>
//                     <p className="empty-hint">Plan routes to see them here</p>
//                 </div>
//                 <div className="navigation-controls single-btn">
//                     <button className="close-button" onClick={toggleDashboard}>Close</button>
//                 </div>
//             </div>
//         );
//     }

//     const currentRoute = routesArray[currentIndex];
//     const optimalRoute = currentRoute.routeData?.optimal_routes?.[0];

//     return (
//         <div className="route-dashboard">
//             <div className="dashboard-header">
//                 <div className="header-left">
//                     <h3>Routes</h3>
//                     <span className="route-count">
//                         {currentIndex + 1} / {routesArray.length}
//                     </span>
//                 </div>
//                 <button className="close-icon-btn" onClick={toggleDashboard}>×</button>
//             </div>

//             <div className="route-info">
//                 <div className="route-title">
//                     <span className="route-icon">📍</span>
//                     <span className="route-name">Route #{currentRoute.id}</span>
//                 </div>

//                 <div className="route-details">
//                     <div className="detail-row">
//                         <span className="detail-label">From:</span>
//                         <span className="detail-value">{currentRoute.source}</span>
//                     </div>
//                     <div className="detail-row">
//                         <span className="detail-label">To:</span>
//                         <span className="detail-value">{currentRoute.destination}</span>
//                     </div>
//                     {currentRoute.intermediates && currentRoute.intermediates.length > 0 && (
//                         <div className="detail-row">
//                             <span className="detail-label">Via:</span>
//                             <span className="detail-value">{currentRoute.intermediates.join(', ')}</span>
//                         </div>
//                     )}
//                     {optimalRoute && (
//                         <>
//                             <div className="detail-row">
//                                 <span className="detail-label">Distance:</span>
//                                 <span className="detail-value">{optimalRoute.distance}</span>
//                             </div>
//                             <div className="detail-row">
//                                 <span className="detail-label">Duration:</span>
//                                 <span className="detail-value">{optimalRoute.duration}</span>
//                             </div>
//                         </>
//                     )}
//                     <div className="detail-row">
//                         <span className="detail-label">Stops:</span>
//                         <span className="detail-value">{currentRoute.waypoints.length}</span>
//                     </div>
//                 </div>
//             </div>

//             <div className="navigation-controls">
//                 <div className="nav-group">
//                     <button
//                         onClick={handlePrevious}
//                         disabled={currentIndex === 0}
//                         className="nav-button secondary"
//                     >
//                         Previous
//                     </button>
//                     <button
//                         onClick={handleNext}
//                         disabled={currentIndex === routesArray.length - 1}
//                         className="nav-button secondary"
//                     >
//                         Next
//                     </button>
//                 </div>

//                 <button className="close-button" onClick={toggleDashboard}>
//                     Close
//                 </button>
//             </div>
//         </div>
//     );
// };
import { useState } from 'react';
import { useAppStore } from '../store/appStore';
import { formatDuration } from '../utils/formatDuration';
import './RouteDashboard.css';

export const RouteDashboard = () => {
    const { activeRoutes } = useAppStore();
    const [currentIndex, setCurrentIndex] = useState(0);
    const [isOpen, setIsOpen] = useState(false); // Default is closed (showing the small button)

    // Convert activeRoutes object to array
    const routesArray = Object.values(activeRoutes);

    // Reset index if current route is removed
    if (currentIndex >= routesArray.length && routesArray.length > 0) {
        setCurrentIndex(0);
    }

    const handleNext = () => {
        if (currentIndex < routesArray.length - 1) {
            setCurrentIndex(currentIndex + 1);
        }
    };

    const handlePrevious = () => {
        if (currentIndex > 0) {
            setCurrentIndex(currentIndex - 1);
        }
    };

    // Define this function BEFORE using it
    const toggleDashboard = () => {
        setIsOpen(!isOpen);
    };

    // 1. Minimized View (The Button)
    // We check this FIRST. If it is not open, we show the button.
    // This satisfies your requirement: "initially when no route is assigned we see the button"
    if (!isOpen) {
        return (
            <div className="route-trigger-container">
                <button className="route-trigger-btn" onClick={toggleDashboard}>
                    <span className="trigger-icon">🗺️</span>
                    <span className="trigger-text">Routes</span>
                    {routesArray.length > 0 && (
                        <span className="trigger-badge">{routesArray.length}</span>
                    )}
                </button>
            </div>
        );
    }

    // 2. Expanded View: Empty State
    // If we are here, isOpen is TRUE. Now we check if we have data.
    if (routesArray.length === 0) {
        return (
            <div className="route-dashboard empty">
                <div className="dashboard-header">
                    <h3>Routes</h3>
                    <button className="close-icon-btn" onClick={toggleDashboard}>×</button>
                </div>
                <div className="empty-state">
                    <div className="empty-icon">🗺️</div>
                    <p className="empty-message">No routes to show</p>
                    <p className="empty-hint">Plan routes to see them here</p>
                </div>
                <div className="navigation-controls single-btn">
                    <button className="close-button" onClick={toggleDashboard}>Close</button>
                </div>
            </div>
        );
    }

    // 3. Expanded View: Data State
    const currentRoute = routesArray[currentIndex];
    const optimalRoute = currentRoute.routeData?.optimal_routes?.[0];

    return (
        <div className="route-dashboard">
            <div className="dashboard-header">
                <div className="header-left">
                    <h3>Routes</h3>
                    <span className="route-count">
                        {currentIndex + 1} / {routesArray.length}
                    </span>
                </div>
                <button className="close-icon-btn" onClick={toggleDashboard}>×</button>
            </div>

            <div className="route-info">
                <div className="route-title">
                    <span className="route-icon">📍</span>
                    <span className="route-name">Route #{currentRoute.id}</span>
                </div>

                <div className="route-details">
                    <div className="detail-row">
                        <span className="detail-label">From:</span>
                        <span className="detail-value">{currentRoute.source}</span>
                    </div>
                    <div className="detail-row">
                        <span className="detail-label">To:</span>
                        <span className="detail-value">{currentRoute.destination}</span>
                    </div>
                    {currentRoute.intermediates && currentRoute.intermediates.length > 0 && (
                        <div className="detail-row">
                            <span className="detail-label">Via:</span>
                            <span className="detail-value">{currentRoute.intermediates.join(', ')}</span>
                        </div>
                    )}
                    {optimalRoute && (
                        <>
                            <div className="detail-row">
                                <span className="detail-label">Distance:</span>
                                <span className="detail-value">{optimalRoute.distance}</span>
                            </div>
                            <div className="detail-row">
                                <span className="detail-label">Duration:</span>
                                <span className="detail-value">{formatDuration(optimalRoute.duration)}</span>
                            </div>
                        </>
                    )}
                    <div className="detail-row">
                        <span className="detail-label">Stops:</span>
                        <span className="detail-value">{currentRoute.waypoints.length}</span>
                    </div>
                </div>
            </div>

            <div className="navigation-controls">
                <div className="nav-group">
                    <button
                        onClick={handlePrevious}
                        disabled={currentIndex === 0}
                        className="nav-button secondary"
                    >
                        Previous
                    </button>
                    <button
                        onClick={handleNext}
                        disabled={currentIndex === routesArray.length - 1}
                        className="nav-button secondary"
                    >
                        Next
                    </button>
                </div>

                <button className="close-button" onClick={toggleDashboard}>
                    Close
                </button>
            </div>
        </div>
    );
};