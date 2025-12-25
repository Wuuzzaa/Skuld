import time

def consume_memory():
    print("Starting memory consumption to trigger OOM...")
    data = []
    i = 0
    try:
        while True:
            # Allocate 100MB chunks
            # 100MB = 100 * 1024 * 1024 bytes
            # 'a' is 1 byte.
            chunk = 'a' * (100 * 1024 * 1024)
            data.append(chunk)
            i += 1
            print(f"Allocated {i * 100} MB")
            time.sleep(0.1)
    except MemoryError:
        print("Caught MemoryError in Python (System might not have killed it yet)")
        # Keep it alive to force OOM killer if MemoryError didn't kill the process
        time.sleep(10)

if __name__ == "__main__":
    consume_memory()
