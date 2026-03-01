"""
Network diagnostic script to identify connectivity issues
"""
import socket
import sys

print("=" * 80)
print("NETWORK DIAGNOSTIC PROTOCOL")
print("=" * 80)

# Test 1: DNS Resolution
print("\n[1] Testing DNS Resolution...")
try:
    ip = socket.gethostbyname('api.binance.com')
    print(f"✓ Successfully resolved api.binance.com → {ip}")
except socket.gaierror as e:
    print(f"✗ DNS Resolution FAILED: {e}")
    sys.exit(1)

# Test 2: Socket connection
print("\n[2] Testing TCP Connection to api.binance.com:443...")
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    sock.connect(('api.binance.com', 443))
    sock.close()
    print("✓ TCP connection successful")
except Exception as e:
    print(f"✗ TCP Connection FAILED: {e}")
    sys.exit(1)

# Test 3: aiohttp DNS
print("\n[3] Testing aiohttp DNS Resolution...")
try:
    import aiohttp
    import asyncio
    
    async def test_aiohttp_dns():
        connector = aiohttp.TCPConnector()
        await connector.resolve_host('api.binance.com')
        await connector.close()
        return True
    
    result = asyncio.run(test_aiohttp_dns())
    if result:
        print("✓ aiohttp DNS resolution successful")
except Exception as e:
    print(f"✗ aiohttp DNS FAILED: {e}")
    print(f"  Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()

# Test 4: Simple aiohttp request
print("\n[4] Testing aiohttp HTTP request...")
try:
    import aiohttp
    import asyncio
    
    async def test_http():
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.binance.com/api/v3/ping', timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return resp.status
    
    status = asyncio.run(test_http())
    print(f"✓ HTTP request successful (status: {status})")
except Exception as e:
    print(f"✗ HTTP request FAILED: {e}")
    print(f"  Error type: {type(e).__name__}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
print("Diagnostic Complete")
print("=" * 80)
