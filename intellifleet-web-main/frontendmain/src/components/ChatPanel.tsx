import { useState, useRef, useEffect } from 'react';
import { useRouteAgent } from '../hooks/useRouteAgent';
import { useAppStore } from '../store/appStore';
import { uploadApi } from '../api/upload';
import apiClient from '../api/client';
import './ChatPanel.css';
import { warehouseApi } from '../api/warehouse';
import { warehousesApi } from '../api/warehouses';
// import { formatDuration } from '../utils/formatDuration';

export const ChatPanel = () => {
  const [input, setInput] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { processMessage, isProcessing } = useRouteAgent();
  //const { chatHistory, addChatMessage, setWarehouses, setVehicles, setWarehouseInventory, setHasCsvUploaded } = useAppStore();
  const { chatHistory, addChatMessage, setWarehouses, setVehicles, setWarehouseInventory, setHasCsvUploaded, setActiveRoutes } = useAppStore();


  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatHistory]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isProcessing || isUploading) return;

    const userMessage = input.trim();
    setInput('');

    // Add user message immediately
    addChatMessage('user', userMessage);

    // Process with agent
    await processMessage(userMessage);
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(e as any);
    }
  };

  // const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
  //   const file = e.target.files?.[0];
  //   if (!file) return;

  //   if (!file.name.endsWith('.csv')) {
  //     addChatMessage('assistant', 'Please upload a valid CSV file.');
  //     return;
  //   }

  //   setIsUploading(true);
  //   addChatMessage('user', `Uploaded file: ${file.name}`);
  //   addChatMessage('assistant', 'Processing CSV file...');

  //   try {
  //     // Clear existing routes and chat when uploading new CSV
  //     clearActiveRoutes();
  //     clearChatHistory();
  //     // 1. Upload CSV
  //     const response = await uploadApi.uploadCSV(file);
  //     if (response.data) {
  //       try {
  //         const inventoryResponse = await warehouseApi.getInventory();
  //         if (inventoryResponse.data) {
  //           setWarehouseInventory(inventoryResponse.data);
  //           setHasCsvUploaded(true);
  //         }
  //       } catch (error) {
  //         console.log("failed to fetch inventory: ", error);
  //       }
  //     }

  //     // After CSV upload, refetch warehouses from API for consistency
  //     try {
  //       const warehousesResponse = await warehousesApi.getWarehouses();
  //       if (warehousesResponse.warehouses) {
  //         const mappedWarehouses = warehousesResponse.warehouses.map((w: any) => ({
  //           ...w,
  //           id: w.warehouse_id
  //         }));
  //         setWarehouses(mappedWarehouses);
  //       }
  //     } catch (err) {
  //       console.error('Failed to refetch warehouses after upload:', err);
  //       // Fallback to upload response data
  //       setWarehouses(response.data);
  //     }

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.endsWith('.csv')) {
      addChatMessage('assistant', 'Please upload a valid CSV file.');
      return;
    }

    setIsUploading(true);
    addChatMessage('user', `Uploaded file: ${file.name}`);
    // addChatMessage('assistant', 'Processing CSV file...');

    try {
      // 1. Upload CSV
      const response = await uploadApi.uploadCSV(file);

      // Clear existing routes and chat when uploading new CSV
      // clearActiveRoutes();
      // clearChatHistory();

      if (!response.message) {
        addChatMessage('assistant', `❌ Upload failed: ${response.message}`);
        console.log("failed to upload csv: ", response);
        return;
      }

      // 2. Check upload_type and refetch appropriate data
      if (response.upload_type === 'warehouse') {
        // --- WAREHOUSE CSV UPLOADED ---

        // Refetch warehouses
        try {
          const warehousesResponse = await warehousesApi.getWarehouses();
          if (warehousesResponse.warehouses) {
            const mappedWarehouses = warehousesResponse.warehouses.map((w: any) => ({
              ...w,
              id: w.warehouse_id
            }));
            setWarehouses(mappedWarehouses);
          }
        } catch (err) {
          console.error('Failed to refetch warehouses:', err);
        }

        // Refetch inventory
        try {
          const inventoryResponse = await warehouseApi.getInventory();
          if (inventoryResponse.data) {
            setWarehouseInventory(inventoryResponse.data);
            setHasCsvUploaded(true);
          }
        } catch (err) {
          console.error('Failed to refetch inventory:', err);
        }

        addChatMessage('assistant', `✅ ${response.message}. Warehouses and inventory updated!`);

      } else if (response.upload_type === 'vehicle') {
        // --- VEHICLE CSV UPLOADED ---

        // Refetch vehicles
        try {
          const vehiclesResponse = await apiClient.get('/vehicles');
          if (vehiclesResponse.data.data.vehicles) {
            console.log("reached correct if block");
            setVehicles(vehiclesResponse.data.data.vehicles);
          }
        } catch (err) {
          console.error('Failed to refetch vehicles:', err);
        }

        let successMessage = `Vehicle CSV uploaded successfully and ✅ ${response.message}.`;
        if (response.missing_warehouses && response.missing_warehouses.length > 0) {
          successMessage += ` Warning: ${response.missing_warehouses.length} warehouses not found.`;
        }
        addChatMessage('assistant', successMessage);
        console.log("success to upload vehicle csv: ", response);

      } else if (response.upload_type === 'route') {
        // --- ROUTE CSV UPLOADED ---

        const allRoutes: Record<number, any> = {};
        const routeData = response.data as any;

        // 1. Map road routes
        if (routeData?.road_routes) {
          routeData.road_routes.forEach((route: any) => {
            allRoutes[route.route_id] = {
              id: route.route_id,
              source: route.source,
              destination: route.destination,
              intermediates: route.intermediate_locations || [],
              waypoints: route.locations || [route.source, route.destination],
              created: new Date(),
              isActive: true,
              routeData: {
                route_id: route.route_id,
                source: route.source,
                destination: route.destination,
                optimal_routes: route.optimal_routes,
                route_cost: route.route_cost ? Number(route.route_cost).toFixed(2) : null,
                source_coords: route.source_coords,
                dest_coords: route.dest_coords,
                distance: route.distance,
                duration: route.duration
              }
            };
          });
        }

        // 2. Map multimodal routes
        if (routeData?.multimodal_routes) {
          routeData.multimodal_routes.forEach((route: any) => {
            const multimodalData = route.data;

            allRoutes[route.route_id] = {
              id: route.route_id,
              source: multimodalData.source,  // Use route-level source (warehouse), not segment source
              destination: multimodalData.destination,  // Use route-level destination (warehouse), not airport
              intermediates: [],
              waypoints: [multimodalData.source, multimodalData.destination],
              created: new Date(),
              isActive: true,
              isMultimodal: true,
              routeData: {
                route_id: route.route_id,
                source: route.source,
                destination: route.destination,
                multimodal: true,
                segments: {
                  segment_1: multimodalData?.segment_1,
                  segment_2: multimodalData?.segment_2,
                  segment_3: multimodalData?.segment_3
                },
                total_distance: multimodalData?.total_distance_km,
                total_duration: multimodalData?.total_duration,
                route_cost: (multimodalData?.total_cost ?? route.total_cost)?.toFixed?.(2) ??
                  Number(multimodalData?.total_cost ?? route.total_cost).toFixed(2)
              }
            };
            console.log("total distance: ", allRoutes[route.route_id].routeData.total_distance_km);
          });
        }

        // 3. Set all routes to the store
        // setActiveRoutes(allRoutes);

        // 3. Merge CSV routes with existing routes (don't overwrite)
        const { activeRoutes } = useAppStore.getState();
        setActiveRoutes({ ...activeRoutes, ...allRoutes });

        const roadCount = routeData?.road_routes?.length || 0;
        const multimodalCount = routeData?.multimodal_routes?.length || 0;

        addChatMessage(
          'assistant',
          `✅ ${response.message} (${roadCount} road routes, ${multimodalCount} multimodal routes loaded)`
        );
        console.log("Route CSV uploaded successfully:", allRoutes);

      } else {
        // Unknown upload type - fallback
        addChatMessage('assistant', `CSV uploaded successfully: ✅ ${response.message}`);
        console.log("CSV upload success (fallback):", response);
      }

    } catch (error: any) {
      console.error('Upload failed:', error);
      addChatMessage('assistant', `❌ Failed to upload CSV: ${error.response?.data?.detail || error.message}`);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };


  return (
    <div className="chat-panel">
      <div className="chat-header">
        <h3>Autonomous Agentic AI Planner</h3>
      </div>
      <div className="chat-messages">
        {chatHistory.length === 0 && (
          <div className="welcome-message">
            <p>👋 <strong>AI Assistant:</strong> I'm your Autonomous Agentic AI Planner</p>
            <p>You can:</p>
            <ul>
              <li>Plan optimal routes between locations both road and air</li>
              <li>Assign vehicles to routes</li>
              <li>Monitor vehicle movements</li>
              <li>query route information to get various details</li>
              <li>Get alternative routes for disruptions</li>
              <li>Change Map View (Satellite view, Street view)</li>
              <li>Clear Map with existing Routes and Vehicles</li>
              <li>Clear Chat</li>
            </ul>
            <p className="sample-csv-note">
              Add your warehouse and inventory instead of the ones present in this sample CSV and then upload it to continue:
            </p>
            <a
              href="/sample_warehouse_data.csv"
              download="sample_warehouse_data.csv"
              className="sample-csv-download"
            >
              📥 Download Sample Warehouse CSV
            </a>

            <p className="sample-csv-note">
              Similarly add your vehicle and capacity details in the below sample csv and upload it to continue:
            </p>
            <a
              href="/sample_vehicle_data.csv"
              download="sample_vehicle_data.csv"
              className="sample-csv-download"
            >
              📥 Download Sample Vehicle CSV
            </a>
            <p className="sample-csv-note">
              If you have multiple route already planned you can add them all in this csv and upload it to create them all at once:
            </p>
            <a
              href="/routes.csv"
              download="routes.csv"
              className="sample-csv-download"
            >
              📥 Download Sample Routes CSV
            </a>
            <p className="note"><strong>Remember:</strong> Upload your warehouse and vehicle CSV file first to enable Autonomous Agentic AI Planner</p>
          </div>
        )}
        {chatHistory.map((msg, idx) => (
          <div key={idx} className={`message-row ${msg.role}`}>
            <div className="message-avatar">
              {msg.role === 'user' ? '👤' : '🤖'}
            </div>
            <div className="message-bubble">
              <div className="message-sender">{msg.role === 'user' ? 'You' : 'AI Assistant'}</div>
              <div className="message-content">{msg.content}</div>
              <div className="message-time">
                {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
              </div>
            </div>
          </div>
        ))}
        {(isProcessing || isUploading) && (
          <div className="message-row assistant">
            <div className="message-avatar">🤖</div>
            <div className="message-bubble typing">
              <div className="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="chat-input-container">
        <div className="unified-input-wrapper">
          <label htmlFor="file-upload" className="file-btn" title="Attach CSV">
            📎
          </label>
          <input
            id="file-upload"
            type="file"
            accept=".csv"
            onChange={handleFileUpload}
            style={{ display: 'none' }}
            disabled={isUploading}
          />

          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Type a message or attach a CSV file..."
            disabled={isProcessing || isUploading}
            rows={1}
          />

          <button
            onClick={handleSend}
            disabled={(!input.trim() && !isUploading) || isProcessing}
            className="send-btn"
          >
            {isProcessing || isUploading ? (
              <span className="loading-spinner"></span>
            ) : (
              '📤'
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

