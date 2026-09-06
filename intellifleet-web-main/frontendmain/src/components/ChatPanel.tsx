import { useState, useRef, useEffect } from 'react';
import { useRouteAgent } from '../hooks/useRouteAgent';
import { useAppStore } from '../store/appStore';
import './ChatPanel.css';
import { NetworkUpload } from './NetworkUpload';
import { CurrentPlanVisuals } from './PlanVisuals';
import { ChatResult } from './ChatResult';
import { chatApi } from '../api/chat';
// import { formatDuration } from '../utils/formatDuration';

export const ChatPanel = () => {
  const [input, setInput] = useState('');
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const { processMessage, isProcessing, startNewSession } = useRouteAgent();
  //const { chatHistory, addChatMessage, setWarehouses, setVehicles, setWarehouseInventory, setHasCsvUploaded } = useAppStore();
  const { chatHistory, addChatMessage, clearChatHistory, warehouses, vehicles, activeRoutes } = useAppStore();
  const persistedRouteCount = Object.values(activeRoutes).filter(route => !route.routeData?.planning).length;
  const networkReady = warehouses.length > 0 && vehicles.length > 0 && persistedRouteCount > 0;

  const handleNewChat = async () => {
    if (isProcessing) return;
    await chatApi.clearChat();
    clearChatHistory();
    useAppStore.getState().clearPlanningVisuals();
    startNewSession();
    setInput('');
  };

  const handleCopy = async (content: string, index: number) => {
    await navigator.clipboard.writeText(content);
    setCopiedIndex(index);
    window.setTimeout(() => setCopiedIndex(current => current === index ? null : current), 1500);
  };


  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatHistory]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isProcessing) return;

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

  /* Legacy single-file CSV ingestion intentionally has no dashboard control.
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
            setWarehouseInventory(inventoryResponse.data.inventory);
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
  */


  return (
    <div className="chat-panel">
      <div className="chat-header">
        <div className="assistant-mark">✦</div>
        <div><h3>UniFleet AI Assistant</h3><span>Powered by deterministic planning</span></div>
        <button className="new-chat-btn" type="button" onClick={handleNewChat} disabled={isProcessing} title="Start a new chat" aria-label="Start a new chat">↻ <span>New Chat</span></button>
      </div>
      <div className={`network-status ${networkReady ? 'ready' : 'empty'}`} role="status">
        {networkReady
          ? <><strong>Network Ready</strong><span>{warehouses.length} Warehouses • {vehicles.length} Vehicles • {persistedRouteCount} Routes</span></>
          : <><strong>Network data has not been uploaded yet.</strong><span>Upload Warehouse, Vehicle and Routes CSVs to start planning.</span></>}
      </div>
      <CurrentPlanVisuals />
      <div className="chat-messages">
        {chatHistory.length === 0 && (
          <div className="welcome-message">
            <p><strong>How can I help with your network?</strong></p>
            <p>Ask me to optimize a shipment, compare modes, evaluate risk, recover from a disruption, or explain a recommendation.</p>
          </div>
        )}
        {chatHistory.map((msg, idx) => (
          <div key={idx} className={`message-row ${msg.role}`}>
            <div className="message-avatar">
              {msg.role === 'user' ? '👤' : '🤖'}
            </div>
            <div className="message-bubble">
              <div className="message-sender">{msg.role === 'user' ? 'You' : 'AI Assistant'}</div>
              {msg.role === 'assistant' ? <ChatResult content={msg.content} /> : <div className="message-content">{msg.content}</div>}
              {msg.role === 'assistant' && <button className="copy-response-btn" type="button" onClick={() => handleCopy(msg.content, idx)} aria-label="Copy complete assistant response">{copiedIndex === idx ? 'Copied' : 'Copy'}</button>}
              <div className="message-time">
                {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
              </div>
            </div>
          </div>
        ))}
        {isProcessing && (
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
      <NetworkUpload />
      <div className="chat-input-container">
        <div className="unified-input-wrapper">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask UniFleet anything…"
            disabled={isProcessing}
            rows={1}
          />

          <button
            onClick={handleSend}
            disabled={!input.trim() || isProcessing}
            className="send-btn"
          >
            {isProcessing ? (
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
