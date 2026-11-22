import struct

# Width, height, decoder sequence, monotonic timestamp, JPEG length.
HEADER = struct.Struct("!IIQQI")
