"""
轻量级 Protobuf Wire Format 解析器
无需 .proto 编译，直接从原始字节解析字段
用于解析抖音/TikTok等平台的WebSocket Protobuf消息
"""
import struct
import gzip
import io


def read_varint(data: bytes, offset: int) -> tuple:
    """读取一个 varint 值，返回 (value, new_offset)"""
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        result |= (byte & 0x7F) << shift
        offset += 1
        if not (byte & 0x80):
            break
        shift += 7
    return result, offset


def parse_fields(data: bytes) -> dict:
    """
    解析 protobuf 数据为 {field_number: [values]} 字典
    wire_type 0 -> int, 1 -> bytes(8), 2 -> bytes(变长), 5 -> bytes(4)
    """
    fields = {}
    offset = 0
    data_len = len(data)
    while offset < data_len:
        try:
            tag, offset = read_varint(data, offset)
        except Exception:
            break
        field_number = tag >> 3
        wire_type = tag & 0x07
        if field_number == 0:
            break
        if wire_type == 0:  # Varint
            value, offset = read_varint(data, offset)
        elif wire_type == 1:  # 64-bit
            value = data[offset:offset + 8]
            offset += 8
        elif wire_type == 2:  # Length-delimited
            length, offset = read_varint(data, offset)
            value = data[offset:offset + length]
            offset += length
        elif wire_type == 5:  # 32-bit
            value = data[offset:offset + 4]
            offset += 4
        else:
            break
        if field_number not in fields:
            fields[field_number] = []
        fields[field_number].append(value)
    return fields


def get_field(fields: dict, num: int, default=None):
    """获取字段的第一个值"""
    vals = fields.get(num)
    if vals:
        return vals[0]
    return default


def get_all_fields(fields: dict, num: int):
    """获取字段的所有值"""
    return fields.get(num, [])


def decode_string(data) -> str:
    """尝试将 bytes 解码为 UTF-8 字符串"""
    if isinstance(data, str):
        return data
    if isinstance(data, int):
        return str(data)
    try:
        return data.decode('utf-8', errors='replace')
    except Exception:
        return str(data)


def varint_to_signed(val: int) -> int:
    """将无符号 varint 转为有符号 (zigzag 或直接)"""
    return val


def decompress_gzip(data: bytes) -> bytes:
    """解压 gzip 数据"""
    try:
        return gzip.decompress(data)
    except Exception:
        return data


def encode_varint(value: int) -> bytes:
    """编码一个 varint"""
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)


def encode_field(field_number: int, wire_type: int, data: bytes) -> bytes:
    """编码一个 protobuf 字段"""
    tag = (field_number << 3) | wire_type
    return encode_varint(tag) + data


def encode_length_delimited(field_number: int, data: bytes) -> bytes:
    """编码 length-delimited 字段"""
    return encode_field(field_number, 2, encode_varint(len(data)) + data)


def encode_varint_field(field_number: int, value: int) -> bytes:
    """编码 varint 字段"""
    return encode_field(field_number, 0, encode_varint(value))


def build_pushframe(payload: bytes, compression: int = 1, seq: int = 1) -> bytes:
    """
    构建抖音/TikTok WebSocket PushFrame
    payload_type=1, compression_type, sequence, payload
    """
    result = bytearray()
    result += encode_varint_field(1, 1)           # payload_type
    result += encode_varint_field(2, compression)  # compression_type
    result += encode_varint_field(3, seq)           # sequence
    result += encode_length_delimited(4, payload)   # payload
    return bytes(result)
