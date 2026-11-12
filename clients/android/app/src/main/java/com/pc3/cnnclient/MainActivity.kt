package com.pc3.cnnclient

import android.graphics.ImageDecoder
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.MediaStore
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID
import java.util.concurrent.Executors

class MainActivity : AppCompatActivity() {

    private val networkExecutor = Executors.newSingleThreadExecutor()
    private lateinit var pixelCanvas: PixelCanvasView
    private lateinit var etHost: EditText
    private lateinit var etPort: EditText
    private lateinit var etTimeout: EditText
    private lateinit var chkInvert: CheckBox
    private lateinit var tvChatLog: TextView

    private val pickImageLauncher =
        registerForActivityResult(ActivityResultContracts.GetContent()) { uri: Uri? ->
            if (uri != null) {
                try {
                    val bitmap = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                        val source = ImageDecoder.createSource(contentResolver, uri)
                        ImageDecoder.decodeBitmap(source) { decoder, _, _ ->
                            decoder.isMutableRequired = true
                        }
                    } else {
                        @Suppress("DEPRECATION")
                        MediaStore.Images.Media.getBitmap(contentResolver, uri)
                    }
                    pixelCanvas.loadFromBitmap(bitmap)
                    appendChat("SISTEMA", "Imagen cargada y escalada a 16x16 píxeles.")
                } catch (e: Exception) {
                    appendChat("ERROR", "No se pudo decodificar la imagen: ${e.message}")
                }
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        pixelCanvas = findViewById(R.id.pixelCanvas)
        etHost = findViewById(R.id.etHost)
        etPort = findViewById(R.id.etPort)
        etTimeout = findViewById(R.id.etTimeout)
        chkInvert = findViewById(R.id.chkInvert)
        tvChatLog = findViewById(R.id.tvChatLog)

        val btnClear: Button = findViewById(R.id.btnClear)
        val btnGallery: Button = findViewById(R.id.btnGallery)
        val btnPing: Button = findViewById(R.id.btnPing)
        val btnSend: Button = findViewById(R.id.btnSend)

        chkInvert.setOnCheckedChangeListener { _, isChecked ->
            pixelCanvas.invertColors = isChecked
        }

        btnClear.setOnClickListener {
            pixelCanvas.clear()
            appendChat("SISTEMA", "Lienzo 16x16 limpiado.")
        }

        btnGallery.setOnClickListener {
            pickImageLauncher.launch("image/*")
        }

        btnPing.setOnClickListener {
            val host = etHost.text.toString()
            val port = etPort.text.toString().toIntOrNull() ?: 9000
            val timeout = etTimeout.text.toString().toIntOrNull() ?: 5000
            val reqId = "android-ping-${UUID.randomUUID().toString().take(8)}"

            appendChat("CLIENTE ->", "PING|$reqId hacia $host:$port")
            networkExecutor.execute {
                try {
                    val (reply, ms) = TcpBinaryClient.ping(host, port, reqId, timeout)
                    runOnUiThread {
                        appendChat("SERVIDOR <-", "$reply (${ms} ms)")
                    }
                } catch (e: Exception) {
                    runOnUiThread {
                        appendChat("ERROR", "${e.message}")
                    }
                }
            }
        }

        btnSend.setOnClickListener {
            val host = etHost.text.toString()
            val port = etPort.text.toString().toIntOrNull() ?: 9000
            val timeout = etTimeout.text.toString().toIntOrNull() ?: 10000
            val reqId = "android-${UUID.randomUUID().toString().take(8)}"
            val vector = pixelCanvas.exportNormalizedVector()

            appendChat("CLIENTE ->", "IDENTIFY|$reqId (256 floats) a $host:$port")
            networkExecutor.execute {
                try {
                    val res = TcpBinaryClient.identify(
                        host = host,
                        port = port,
                        requestId = reqId,
                        pixels256 = vector,
                        mode = "DISTRIBUTED",
                        timeoutMs = timeout
                    )
                    val summary = String.format(
                        Locale.US,
                        "Predicción: %s | Círculo=%.1f%%, Cruz=%.1f%%, Triángulo=%.1f%% (%d ms)",
                        res.label,
                        res.pCircle * 100.0,
                        res.pCross * 100.0,
                        res.pTriangle * 100.0,
                        res.latencyMs
                    )
                    runOnUiThread {
                        appendChat("SERVIDOR <-", summary)
                    }
                } catch (e: Exception) {
                    runOnUiThread {
                        appendChat("ERROR", "${e.message}")
                    }
                }
            }
        }
    }

    private fun appendChat(sender: String, message: String) {
        val time = SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(Date())
        val line = "[$time] $sender: $message\n\n"
        tvChatLog.append(line)
    }

    override fun onDestroy() {
        super.onDestroy()
        networkExecutor.shutdownNow()
    }
}
