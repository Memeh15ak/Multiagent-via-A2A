# test_websocket_fixed.py - Comprehensive WebSocket testing

import asyncio
import json
import time
from server.websocket_client import WebSocketClient
from loguru import logger


async def test_basic_connection():
    """Test basic WebSocket connection and heartbeat"""
    print("🧪 Testing Basic Connection...")
    
    client = WebSocketClient("ws://127.0.0.1:5000/ws")
    
    # Connect
    success = await client.connect()
    if not success:
        print("❌ Connection failed")
        return False
    
    print("✅ Connected successfully")
    
    # Wait for heartbeat exchange
    print("⏱️ Waiting for heartbeat exchange...")
    await asyncio.sleep(35)  # Wait longer than heartbeat interval
    
    if client.connected:
        print("✅ Survived heartbeat check!")
        stats = client.get_stats()
        print(f"📊 Pings received: {stats['pings_received']}")
        print(f"📊 Pongs sent: {stats['pongs_sent']}")
    else:
        print("❌ Connection lost during heartbeat")
        return False
    
    await client.disconnect()
    return True


async def test_query_processing():
    """Test query processing functionality"""
    print("\n🧪 Testing Query Processing...")
    
    client = WebSocketClient("ws://127.0.0.1:5000/ws")
    
    if not await client.connect():
        print("❌ Connection failed")
        return False
    
    # Test different query types
    queries = [
        "weather today",
        "what's the temperature in New York?",
        "system status",
        "tell me about data analysis"
    ]
    
    for query in queries:
        print(f"\n📝 Testing query: '{query}'")
        
        # Send as plain text query
        await client.send_plain_text_query(query)
        
        # Wait for response
        await asyncio.sleep(3)
    
    # Test JSON query format
    print(f"\n📝 Testing JSON query format...")
    success, query_id = await client.send_query("weather in London")
    
    if success:
        print(f"✅ JSON query sent with ID: {query_id}")
        await asyncio.sleep(3)
    
    await client.disconnect()
    return True


async def test_error_handling():
    """Test error handling and recovery"""
    print("\n🧪 Testing Error Handling...")
    
    client = WebSocketClient("ws://127.0.0.1:5000/ws")
    
    if not await client.connect():
        print("❌ Connection failed")
        return False
    
    # Test invalid JSON
    try:
        await client.websocket.send("invalid json {")
        await asyncio.sleep(1)
        print("✅ Server handled invalid JSON gracefully")
    except Exception as e:
        print(f"⚠️ Error sending invalid JSON: {e}")
    
    # Test empty query
    await client.send_query("")
    await asyncio.sleep(1)
    
    await client.disconnect()
    return True


async def test_status_requests():
    """Test status request functionality"""
    print("\n🧪 Testing Status Requests...")
    
    client = WebSocketClient("ws://127.0.0.1:5000/ws")
    
    if not await client.connect():
        print("❌ Connection failed")
        return False
    
    # Request status
    print("📊 Requesting server status...")
    await client.request_status()
    
    # Wait for response
    await asyncio.sleep(2)
    
    await client.disconnect()
    return True


async def test_concurrent_connections():
    """Test multiple concurrent connections"""
    print("\n🧪 Testing Concurrent Connections...")
    
    clients = []
    
    # Create multiple clients
    for i in range(3):
        client = WebSocketClient("ws://127.0.0.1:5000/ws")
        if await client.connect():
            clients.append(client)
            print(f"✅ Client {i+1} connected")
        else:
            print(f"❌ Client {i+1} failed to connect")
    
    if not clients:
        print("❌ No clients connected")
        return False
    
    # Send queries from all clients
    tasks = []
    for i, client in enumerate(clients):
        task = client.send_plain_text_query(f"test query from client {i+1}")
        tasks.append(task)
    
    await asyncio.gather(*tasks)
    
    # Wait for responses
    await asyncio.sleep(5)
    
    # Check connection stats
    for i, client in enumerate(clients):
        stats = client.get_stats()
        print(f"📊 Client {i+1} stats: {stats['messages_sent']} sent, {stats['messages_received']} received")
    
    # Disconnect all
    for client in clients:
        await client.disconnect()
    
    return True


async def test_long_running_connection():
    """Test long-running connection stability"""
    print("\n🧪 Testing Long-Running Connection...")
    
    client = WebSocketClient("ws://127.0.0.1:5000/ws")
    
    if not await client.connect():
        print("❌ Connection failed")
        return False
    
    # Run for 2 minutes with periodic queries
    start_time = time.time()
    query_count = 0
    
    try:
        while time.time() - start_time < 120:  # 2 minutes
            if query_count % 10 == 0:  # Every 10th iteration
                await client.send_plain_text_query(f"periodic query {query_count}")
                print(f"📝 Sent periodic query {query_count}")
            
            await asyncio.sleep(5)  # Wait 5 seconds between checks
            query_count += 1
            
            if not client.connected:
                print("❌ Connection lost during long-running test")
                return False
        
        print("✅ Long-running connection test completed successfully")
        stats = client.get_stats()
        print(f"📊 Final stats: {json.dumps(stats, indent=2)}")
        
    except KeyboardInterrupt:
        print("🛑 Long-running test interrupted")
    
    await client.disconnect()
    return True


async def run_all_tests():
    """Run all WebSocket tests"""
    print("🚀 Starting WebSocket Test Suite")
    print("=" * 50)
    
    tests = [
        ("Basic Connection & Heartbeat", test_basic_connection),
        ("Query Processing", test_query_processing),
        ("Error Handling", test_error_handling),
        ("Status Requests", test_status_requests),
        ("Concurrent Connections", test_concurrent_connections),
        # ("Long-Running Connection", test_long_running_connection),  # Uncomment for full test
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = await test_func()
            results[test_name] = "✅ PASSED" if result else "❌ FAILED"
        except Exception as e:
            results[test_name] = f"❌ ERROR: {e}"
            logger.error(f"Test '{test_name}' failed with error: {e}")
    
    # Print summary
    print(f"\n{'='*50}")
    print("📊 TEST SUMMARY")
    print(f"{'='*50}")
    
    for test_name, result in results.items():
        print(f"{test_name}: {result}")
    
    passed = sum(1 for result in results.values() if result.startswith("✅"))
    total = len(results)
    
    print(f"\n🎯 Overall: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All tests passed!")
    else:
        print("⚠️ Some tests failed - check logs for details")


if __name__ == "__main__":
    # Configure logging
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
        level="INFO"
    )
    
    # Add option to run individual tests
    import sys
    
    if len(sys.argv) > 1:
        test_name = sys.argv[1].lower()
        if test_name == "basic":
            asyncio.run(test_basic_connection())
        elif test_name == "query":
            asyncio.run(test_query_processing())
        elif test_name == "error":
            asyncio.run(test_error_handling())
        elif test_name == "status":
            asyncio.run(test_status_requests())
        elif test_name == "concurrent":
            asyncio.run(test_concurrent_connections())
        elif test_name == "long":
            asyncio.run(test_long_running_connection())
        else:
            print(f"Unknown test: {test_name}")
            print("Available tests: basic, query, error, status, concurrent, long")
    else:
        # Run all tests
        asyncio.run(run_all_tests())