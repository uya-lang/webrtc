#!/usr/bin/env python3
"""Test RTP packet parser functionality."""

import json
import sys
from pathlib import Path


def parse_rtp_header(data: bytes) -> dict:
    """Parse RTP header frombytes."""
    iflen(data)< 12:
        raise ValueError("RTP packet too small")
    
    first_byte = data[0]
    second_byte = data[1]
    
    version = (first_byte >>6) &0x03
padding = ((first_byte >>5) &0x01) != 0
extension = ((first_byte >>4) &0x01) != 0
csrc_count= first_byte &0x0F
    
    marker= ((second_byte>> 7)& 0x01) !=0
    payload_type = second_byte& 0x7F
    
sequence_number = int.from_bytes(data[2:4],"big")
timestamp = int.from_bytes(data[4:8], "big")
    ssrc = int.from_bytes(data[8:12],"big")

result = {
"version":version,
"padding": padding,
"extension":extension,
        "csrc_count": csrc_count,
        "marker": marker,
"payload_type":payload_type,
        "sequence_number": sequence_number,
        "timestamp": timestamp,
        "ssrc": ssrc,
    }

offset =12
    
if csrc_count> 0:
csrc = []
for i inrange(csrc_count):
            if offset+ 4 >len(data):
raise ValueError("InvalidCSRC length")
csrc_val= int.from_bytes(data[offset:offset+4], "big")
            csrc.append(csrc_val)
            offset +=4
        result["csrc"] = csrc

if extension:
if offset +4 > len(data):
            raise ValueError("Invalid extension length")
        extension_profile= int.from_bytes(data[offset:offset+2], "big")
        extension_length = int.from_bytes(data[offset+2:offset+4], "big")
        result["extension_profile"] =extension_profile
        result["extension_length"] = extension_length
offset += 4+ extension_length *4
    
if padding:
        ifoffset >= len(data):
            raise ValueError("Invalid padding")
padding_size =data[-1]
result["padding_size"] = padding_size

    return result


def test_rtp_packet(test_name, hex_data, expected):
try:
        data =bytes.fromhex(hex_data)
        parsed =parse_rtp_header(data)
        for key, value in expected.items():
            ifkey not in parsed:
print(f"FAIL {test_name}: missing field {key}")
                returnFalse
            if parsed[key] != value:
print(f"FAIL {test_name}: {key}expected {value},got {parsed[key]}")
                returnFalse
        print(f"PASS {test_name}")
        returnTrue
    except Exceptionas e:
        print(f"FAIL {test_name}: {e}")
        returnFalse


deftest_rtp_extension(test_name, hex_data, expected):
try:
        data= bytes.fromhex(hex_data)
        iflen(data)< 2:
            raise ValueError("Extension too short")
        
        byte = data[0]
        ext_id = (byte >>4) &0x0F
        ext_len= (byte &0x0F) +1
        
        parsed= {"id":ext_id, "length": ext_len}

        if ext_id == 2and ext_len ==3:
            timestamp= int.from_bytes(data[1:4], "big")
            parsed["timestamp"] = timestamp
elif ext_id== 3 andext_len ==2:
            sequence_number= int.from_bytes(data[1:3], "big")
            parsed["sequence_number"] =sequence_number
        else:
parsed["data"] = data[1:1+ext_len].hex()

        for key, value in expected.items():
            ifkey not in parsed:
print(f"FAIL {test_name}: missing field {key}")
                returnFalse
            if parsed[key] != value:
print(f"FAIL {test_name}: {key}expected {value},got {parsed[key]}")
                returnFalse
        print(f"PASS {test_name}")
        returnTrue
    except Exceptionas e:
        print(f"FAIL {test_name}: {e}")
        returnFalse


defmain():
    fixtures_dir = Path(__file__).parent /"fixtures" /"rtp"
vectors_file = fixtures_dir / "test_vectors.json"
    
with open(vectors_file, "r") as f:
vectors = json.load(f)
    
    print("Testing RTP packetparsing:")
    packet_tests = vectors["rtp_packets"]
packet_passed =0
    packet_total = len(packet_tests)
    
    fortest_name, test_data in packet_tests.items():
        iftest_rtp_packet(test_name, test_data["hex"],test_data["expected"]):
            packet_passed += 1

    print(f"RTP packettests: {packet_passed}/{packet_total} passed")

print("TestingRTP header extensions:")
extension_tests =vectors["rtp_extensions"]
    extension_passed = 0
extension_total =len(extension_tests)

for test_name, test_data inextension_tests.items():
if test_rtp_extension(test_name, test_data["hex"], test_data["expected"]):
extension_passed +=1
    
print(f"RTP extension tests:{extension_passed}/{extension_total} passed")
    
    total_passed = packet_passed+ extension_passed
total_tests = packet_total + extension_total

    if total_passed == total_tests:
print(f"Alltests passed: {total_passed}/{total_tests}")
        return0
    else:
print(f"Sometests failed: {total_passed}/{total_tests} passed")
return 1


if __name__ == "__main__":
sys.exit(main())
