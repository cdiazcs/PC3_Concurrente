package com.pc3.cnnclient

import java.io.DataInputStream
import java.io.DataOutputStream
import java.io.EOFException
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket
import java.nio.charset.StandardCharsets
import java.util.Locale

data class InferenceResponse(
    val requestId: String,
    val label: String,
    val pCircle: Double,
    val pCross: Double,
    val pTriangle: Double,
    val latencyMs: Long,
    val rawFrame: String
)

object TcpBinaryClient {
    private const val MAX_FRAME_BYTES = 2_000_000

    fun validateEndpoint(host: String, port: Int) {
        val cleanHost = host.trim().lowercase(Locale.ROOT)
        require(cleanHost.isNotEmpty()) { "El host no puede estar vacío." }
        require(cleanHost != "localhost" && cleanHost != "127.0.0.1") {
            "No uses localhost/127.0.0.1 en Android; usa 10.0.2.2 (emulador) o la IP LAN del servidor."
        }
        require(port in 1..65535) { "Puerto inválido: $port" }
    }

    fun ping(host: String, port: Int, requestId: String, timeoutMs: Int = 5000): Pair<String, Long> {
        validateEndpoint(host, port)
        val t0 = System.nanoTime()
        val reply = sendFrame(host.trim(), port, "PING|$requestId", timeoutMs)
        val ms = (System.nanoTime() - t0) / 1_000_000L
        return reply to ms
    }

    fun identify(
        host: String,
        port: Int,
        requestId: String,
        pixels256: FloatArray,
        mode: String = "DISTRIBUTED",
        timeoutMs: Int = 10000
    ): InferenceResponse {
        validateEndpoint(host, port)
        require(pixels256.size == 256) { "Se requieren exactamente 256 valores (16x16)." }

        val vectorStr = pixels256.joinToString(",") { value ->
            String.format(Locale.US, "%.4f", value.coerceIn(0f, 1f))
        }
        val payload = "IDENTIFY|$requestId|$vectorStr|$mode"

        val t0 = System.nanoTime()
        val raw = sendFrame(host.trim(), port, payload, timeoutMs)
        val elapsedMs = (System.nanoTime() - t0) / 1_000_000L

        val parts = raw.split("|")
        if (parts.isEmpty()) throw IOException("Respuesta vacía del servidor.")
        if (parts[0] == "ERROR") {
            val code = parts.getOrElse(2) { "error_desconocido" }
            throw IOException("Servidor rechazó $requestId: $code")
        }
        if (parts[0] != "RESULT" || parts.size < 5) {
            throw IOException("Trama inesperada: $raw")
        }

        val probs = parts[4].split(",")
        if (probs.size < 3) throw IOException("Probabilidades incompletas: ${parts[4]}")

        val pCircle = probs[0].toDoubleOrNull() ?: 0.0
        val pCross = probs[1].toDoubleOrNull() ?: 0.0
        val pTriangle = probs[2].toDoubleOrNull() ?: 0.0

        val maxProb = maxOf(pCircle, pCross, pTriangle)
        val label = when (maxProb) {
            pCircle -> "Círculo"
            pCross -> "Cruz"
            else -> "Triángulo"
        }

        return InferenceResponse(
            requestId = parts[1],
            label = label,
            pCircle = pCircle,
            pCross = pCross,
            pTriangle = pTriangle,
            latencyMs = elapsedMs,
            rawFrame = raw
        )
    }

    private fun sendFrame(host: String, port: Int, message: String, timeoutMs: Int): String {
        val body = message.toByteArray(StandardCharsets.UTF_8)
        require(body.size <= MAX_FRAME_BYTES) { "Mensaje excede límite de 2,000,000 bytes." }

        Socket().use { socket ->
            socket.soTimeout = timeoutMs
            socket.connect(InetSocketAddress(host, port), timeoutMs)

            val out = DataOutputStream(socket.getOutputStream())
            val input = DataInputStream(socket.getInputStream())

            out.writeInt(body.size)
            out.write(body)
            out.flush()

            val respLen = try {
                input.readInt()
            } catch (e: EOFException) {
                throw IOException("Conexión cerrada por el servidor sin cabecera de respuesta.", e)
            }

            if (respLen <= 0 || respLen > MAX_FRAME_BYTES) {
                throw IOException("Longitud de respuesta inválida: $respLen bytes")
            }

            val respBytes = ByteArray(respLen)
            input.readFully(respBytes)
            return String(respBytes, StandardCharsets.UTF_8)
        }
    }
}
