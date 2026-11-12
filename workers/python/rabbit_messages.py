"""Contrato de la rama y adaptacion explicita del backend 8901cfb, sin AMQP."""
import base64
import binascii
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import struct

from cnn_python.images import PNG, decode_image, normalize
from cnn_python.model import CLASSES, vector


class MessageError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class TemporaryError(RuntimeError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def valid_id(value):
    return (isinstance(value, str) and 0 < len(value) <= 128
            and all(not c.isspace() and c not in '|,' and ord(c) >= 32 for c in value))


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MessageError('duplicate_json_key')
        result[key] = value
    return result


def parse(body, config):
    if not isinstance(body, bytes) or len(body) > config.max_message:
        raise MessageError('message_size')
    try:
        value = json.loads(body, object_pairs_hook=_unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(MessageError('nonfinite_json')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise MessageError(getattr(exc, 'code', 'invalid_json')) from None
    if not isinstance(value, dict):
        raise MessageError('json_object_required')
    return value


@dataclass(frozen=True)
class Request:
    request_id: str
    client_id: str
    model: str
    profile: str
    mode: str
    pixels: tuple
    fingerprint: str


def validate(value, config, correlation_id=None):
    if not valid_id(value.get('idSolicitud')) or not valid_id(value.get('idCliente')):
        raise MessageError('invalid_request_or_client_id')
    if correlation_id is not None and correlation_id != value['idSolicitud']:
        raise MessageError('correlation_mismatch')
    if type(value.get('schemaVersion')) is not int or value['schemaVersion'] != 1:
        raise MessageError('schema_version')
    if value.get('modeloDestino') != config.model:
        raise MessageError('unknown_model')
    if type(value.get('intento', 1)) is not int or not 1 <= value.get('intento', 1) <= 10:
        raise MessageError('invalid_attempt')
    try:
        timestamp = datetime.fromisoformat(value['timestamp'].replace('Z', '+00:00'))
        if timestamp.utcoffset() is None:
            raise ValueError()
    except (KeyError, ValueError, TypeError, AttributeError):
        raise MessageError('invalid_timestamp') from None
    payload = value.get('payload')
    if not isinstance(payload, dict):
        raise MessageError('invalid_payload')
    mode = payload.get('modo', 'SEQUENTIAL')
    if mode not in ('SEQUENTIAL', 'DISTRIBUTED'):
        raise MessageError('invalid_mode')
    if value.get('tipo') == 'INFERENCIA':
        profile = 'backend-8901cfb'
        raw = value.get('imagenBase64')
        if not isinstance(raw, str) or len(raw) > 20000:
            raise MessageError('invalid_pixels')
        try:
            pixels = vector(raw.split(','), 256, normalized=True)
        except (ValueError, OverflowError):
            raise MessageError('invalid_pixels') from None
    elif value.get('tipo') == 'CLASIFICAR_IMAGEN':
        profile = 'repository-v1'
        raw = payload.get('imagenBase64')
        if not isinstance(raw, str) or len(raw) > 4*((config.max_image+2)//3):
            raise MessageError('image_size')
        try:
            image = base64.b64decode(raw, validate=True)
        except (ValueError, binascii.Error):
            raise MessageError('invalid_base64') from None
        if not 0 < len(image) <= config.max_image:
            raise MessageError('image_size')
        mime = payload.get('mimeType')
        if mime not in ('image/png', 'image/x-portable-graymap'):
            raise MessageError('unsupported_mime_type')
        if mime == 'image/png':
            if not image.startswith(PNG) or len(image) < 24:
                raise MessageError('invalid_image')
            w, h = struct.unpack('!II', image[16:24])
            if not w or not h or w*h > config.max_pixels:
                raise MessageError('image_dimensions')
        elif not image.startswith((b'P2', b'P5')):
            raise MessageError('invalid_image')
        try:
            raster = decode_image(image)
            if raster.width*raster.height > config.max_pixels:
                raise MessageError('image_dimensions')
            pixels = normalize(raster)
        except (ValueError, OverflowError, IndexError) as exc:
            raise MessageError(getattr(exc, 'code', 'invalid_image')) from None
    else:
        raise MessageError('unknown_message_type')
    identity = [value['idCliente'], config.model, profile, mode, pixels]
    digest = hashlib.sha256(encode(identity)).hexdigest()
    return Request(value['idSolicitud'], value['idCliente'], config.model, profile, mode, tuple(pixels), digest)


def response(request, probabilities, inference_ms, weights_hash):
    probabilities = vector(probabilities, 3)
    if any(p < 0 or p > 1 for p in probabilities) or abs(sum(probabilities)-1) > 1e-8:
        raise TemporaryError('invalid_inference_result')
    index = max(range(3), key=probabilities.__getitem__)
    return {'schemaVersion': 1, 'tipo': 'RESULTADO_CLASIFICACION',
            'idSolicitud': request.request_id, 'idCliente': request.client_id,
            'modeloDestino': request.model, 'timestamp': utc_now(), 'estado': 'COMPLETADA',
            'versionPesos': weights_hash, 'error': None,
            'payload': {'etiqueta': CLASSES[index], 'probabilidad': probabilities[index],
                        'probabilidades': list(probabilities) if request.profile == 'backend-8901cfb'
                        else dict(zip(CLASSES, probabilities)), 'duracionMs': inference_ms}}


def error_response(value, code):
    request_id = value.get('idSolicitud') if isinstance(value, dict) else None
    return {'schemaVersion': 1, 'tipo': 'RESULTADO_CLASIFICACION',
            'idSolicitud': request_id if valid_id(request_id) else None,
            'idCliente': value.get('idCliente') if isinstance(value, dict) and valid_id(value.get('idCliente')) else None,
            'modeloDestino': 'A', 'timestamp': utc_now(), 'estado': 'ERROR',
            'error': code, 'payload': {'codigo': code, 'descripcion': code}}
