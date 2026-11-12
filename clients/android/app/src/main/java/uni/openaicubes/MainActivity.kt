package uni.openaicubes

import android.app.Activity
import android.os.Bundle
import android.content.Intent
import android.graphics.BitmapFactory
import android.widget.*
import java.io.DataInputStream
import java.io.DataOutputStream
import java.net.InetSocketAddress
import java.net.Socket
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

class MainActivity : Activity() {
    private val executor = Executors.newSingleThreadExecutor()
    private val deadlines = Executors.newSingleThreadScheduledExecutor()
    private lateinit var host: EditText
    private lateinit var port: EditText
    private lateinit var client: EditText
    private lateinit var chat: TextView
    private lateinit var preview: ImageView
    private lateinit var send: Button
    private var image: ByteArray? = null
    private var mime = "image/png"
    @Volatile private var active: Socket? = null

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val prefs = getPreferences(MODE_PRIVATE)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(24,40,24,24) }
        fun field(hintText: String, value: String): EditText = EditText(this).apply { hint=hintText;setSingleLine();setText(value);root.addView(this) }
        root.addView(TextView(this).apply { text="OpenAI Cubes · Chat de imágenes";textSize=22f })
        host=field("Host backend (IP o MagicDNS)",prefs.getString("host","") ?: "")
        port=field("Puerto",prefs.getString("port","9000") ?: "9000")
        client=field("Identificación de cliente",prefs.getString("client","cliente-android-01") ?: "cliente-android-01")
        preview=ImageView(this);root.addView(preview,LinearLayout.LayoutParams(-1,220))
        root.addView(Button(this).apply { text="Seleccionar imagen";setOnClickListener {
            startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply { type="image/*";addCategory(Intent.CATEGORY_OPENABLE) },1)
        } })
        send=Button(this).apply { text="Enviar";isEnabled=false;setOnClickListener { submit() } };root.addView(send)
        chat=TextView(this).apply { text="Configura el backend privado y selecciona una imagen.\n" }
        root.addView(ScrollView(this).apply { addView(chat) },LinearLayout.LayoutParams(-1,0,1f))
        setContentView(root)
    }
    override fun onActivityResult(requestCode: Int,resultCode: Int,data: Intent?) {
        super.onActivityResult(requestCode,resultCode,data)
        if(requestCode!=1 || resultCode!=RESULT_OK)return
        val uri=data?.data ?: return
        executor.execute {
            try {
                val bytes=contentResolver.openInputStream(uri)!!.use { input ->
                    val output=java.io.ByteArrayOutputStream()
                    val buffer=ByteArray(8192)
                    while(output.size()<=1_000_000) {
                        val count=input.read(buffer)
                        if(count<0)break
                        output.write(buffer,0,count)
                    }
                    output.toByteArray() }
                require(bytes.isNotEmpty() && bytes.size<=1_000_000) { "Imagen hasta 1 MB" }
                val bounds=BitmapFactory.Options().apply { inJustDecodeBounds=true }
                BitmapFactory.decodeByteArray(bytes,0,bytes.size,bounds)
                require(bounds.outWidth>0 && bounds.outHeight>0 && bounds.outWidth.toLong()*bounds.outHeight<=4_194_304) { "Imagen inválida o demasiado grande" }
                val detected=if(bytes[0]==0x89.toByte()) "image/png" else "image/jpeg"
                require(bounds.outMimeType==detected) { "Usa PNG o JPEG" }
                val bitmap=BitmapFactory.decodeByteArray(bytes,0,bytes.size)
                runOnUiThread { image=bytes;mime=detected;preview.setImageBitmap(bitmap);send.isEnabled=true;chat.append("Imagen preparada.\n") }
            } catch(e: Exception) { runOnUiThread { chat.append("Error: ${e.message}\n") } }
        }
    }
    private fun submit() {
        val bytes=image ?: return
        val destination=host.text.toString().trim()
        val clientId=client.text.toString().trim()
        val number=port.text.toString().toIntOrNull()
        if(destination.isEmpty() || number==null || number !in 1..65535 || !Protocol.validId(clientId)) {
            chat.append("Revisa host, puerto e identificación.\n");return
        }
        val id="android-${UUID.randomUUID()}"
        val request=Protocol.request(id,clientId,"SEQUENTIAL",mime,bytes)
        getPreferences(MODE_PRIVATE).edit().putString("host",destination).putString("port",number.toString()).putString("client",clientId).apply()
        send.isEnabled=false;chat.append("Tú: imagen [$id]\nValidando, clasificando y esperando persistencia…\n")
        executor.execute {
            try {
                Socket().use { socket ->
                    active=socket
                    val deadline=deadlines.schedule({ socket.close() },80,TimeUnit.SECONDS)
                    try {
                        socket.connect(InetSocketAddress(destination,number),5000);socket.soTimeout=80000
                        Protocol.write(DataOutputStream(socket.getOutputStream()),request)
                        val result=Protocol.result(Protocol.read(DataInputStream(socket.getInputStream())),id)
                        runOnUiThread { chat.append("Sistema: ${result.label} · ${"%.2f".format(result.probability*100)}% · persistencia confirmada\n") }
                    } finally { deadline.cancel(false);active=null }
                }
            } catch(e: Exception) { runOnUiThread { chat.append("Error o timeout: ${e.message}\n") } }
            finally { runOnUiThread { send.isEnabled=image!=null } }
        }
    }
    override fun onDestroy() { runCatching { active?.close() };executor.shutdownNow();deadlines.shutdownNow();super.onDestroy() }
}
