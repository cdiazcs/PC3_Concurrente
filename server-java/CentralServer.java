import java.io.*;
import java.net.*;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.regex.Pattern;

// NUEVAS IMPORTACIONES
import models.MensajesRabbit;
import messaging.RabbitMQManager;
import db.PostgresManager;

public class CentralServer {
    private static final int MAX_BYTES = 2_000_000;
    private static final int CLIENT_TIMEOUT_MS = 30000;
    private static final Pattern DECIMAL = Pattern.compile("[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?");
    private static final AtomicInteger cursor = new AtomicInteger();
    private static final List<Node> workers = new ArrayList<>();
    private static DistributedCnn distributed;
    
    // NUEVOS GESTORES
    private static RabbitMQManager rabbit;
    private static PostgresManager postgres;
    
    private static final ScheduledThreadPoolExecutor deadlines = new ScheduledThreadPoolExecutor(1, task -> {
        Thread thread = new Thread(task, "socket-deadlines");
        thread.setDaemon(true);
        return thread;
    });
    static { deadlines.setRemoveOnCancelPolicy(true); }

    private static class Node {
        final InetSocketAddress endpoint;
        volatile long skipIdentifyUntil;
        Node(String host, int port) { endpoint = new InetSocketAddress(host, port); }
        public String toString() { return endpoint.toString(); }
    }

    private static class InvalidWorkerResponse extends IOException {
        InvalidWorkerResponse() { super("invalid_worker_response"); }
    }

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            System.err.println("Uso: java CentralServer <puerto> <hostWorker:puerto> [otros...]");
            return;
        }
        int port = Integer.parseInt(args[0]);
        for (int i = 1; i < args.length; i++) {
            int idx = args[i].lastIndexOf(':');
            if (idx < 1) throw new IllegalArgumentException("worker debe ser host:puerto");
            workers.add(new Node(args[i].substring(0,idx), Integer.parseInt(args[i].substring(idx+1))));
        }
        List<InetSocketAddress> endpoints = new ArrayList<>();
        for (Node node : workers) endpoints.add(node.endpoint);
        distributed = new DistributedCnn(endpoints, 10000, 12000);
        
        // INICIALIZAR RABBITMQ Y POSTGRESQL
        System.out.println("Iniciando conexiones a RabbitMQ y PostgreSQL...");
        // Asegúrate de que los datos de Postgres coincidan con los tuyos
        postgres = new PostgresManager("localhost", 5432, "pc3_concurrente", "postgres", "postgresql17");
        rabbit = new RabbitMQManager("localhost", 5672);
        System.out.println("Conexiones listas.");

        int maxClients = Integer.getInteger("openaicubes.maxClients", 64);
        if (maxClients < 1 || maxClients > 1024) throw new IllegalArgumentException("invalid_max_clients");
        
        ExecutorService clients = new ThreadPoolExecutor(Math.min(16, maxClients), maxClients,
            30, TimeUnit.SECONDS, new SynchronousQueue<Runnable>());
        try (ServerSocket listener = new ServerSocket(port)) {
            System.out.println("CentralServer en " + port + ", workers=" + workers);
            while (true) {
                Socket socket = listener.accept();
                try { clients.execute(() -> handle(socket)); }
                catch (RejectedExecutionException busy) {
                    socket.close();
                    System.err.println("Conexion rechazada: client_limit");
                }
            }
        } finally { clients.shutdown(); distributed.close(); deadlines.shutdownNow(); }
    }

    private static void handle(Socket socket) {
        try (Socket client = socket;
             DataInputStream input = new DataInputStream(new BufferedInputStream(client.getInputStream()));
             DataOutputStream output = new DataOutputStream(new BufferedOutputStream(client.getOutputStream()))) {
            client.setSoTimeout(CLIENT_TIMEOUT_MS);
            while (true) {
                ScheduledFuture<?> guard = closeAfter(client, CLIENT_TIMEOUT_MS);
                try {
                    String request;
                    try { request = read(input); }
                    catch (EOFException ex) { return; }
                    String[] fields = request.split("\\|", -1);
                    String id = fields.length > 1 ? fields[1] : "unknown";
                    String reply;
                    
                    if (fields[0].equals("CONFIG") && fields.length == 2 && validId(id)) {
                        try { reply = distributed.configuration(id); }
                        catch (DistributedCnn.Failure failure) { reply = "ERROR|"+id+"|"+failure.code; }
                    } else if (fields[0].equals("IDENTIFY")) {
                        String invalid = validateIdentify(fields);
                        if (invalid != null) {
                            reply = invalid;
                        } else {
                            // AQUI ESTA LA MAGIA: En lugar del socket, usamos RabbitMQ
                            reply = procesarConRabbitMQ(id, fields[2]);
                        }
                    } else if (fields.length >= 2 && Arrays.asList("PING", "CONV", "MLP").contains(fields[0])) {
                        try { reply = forward(request); }
                        catch (IOException ex) { reply = "ERROR|" + id + "|no_worker_available"; }
                    } else reply = "ERROR|" + id + "|unsupported_command";
                    
                    write(output, reply);
                } finally { guard.cancel(false); }
            }
        } catch (IOException ex) { System.err.println("Cliente desconectado: " + ex.getMessage()); }
    }

    // =========================================================
    // NUEVO MÉTODO: ORQUESTADOR DE RABBITMQ Y POSTGRES
    // =========================================================
    public static String procesarConRabbitMQ(String clientId, String pixels) {
        String idSolicitud = UUID.randomUUID().toString();
        try {
            // 1. Guardar en BD (RECIBIDA)
            postgres.guardarSolicitud(idSolicitud, clientId, "A", "RECIBIDA");

            // 2. Preparar el JSON para RabbitMQ
            MensajesRabbit.PeticionIA peticion = new MensajesRabbit.PeticionIA();
            peticion.idSolicitud = idSolicitud;
            peticion.idCliente = clientId;
            peticion.modeloDestino = "A";
            peticion.imagenBase64 = pixels; // Enviamos los 256 pixeles
            peticion.timestamp = java.time.Instant.now().toString();

            // 3. Enviar a RabbitMQ y esperar respuesta
            System.out.println("Enviando tarea " + idSolicitud + " a RabbitMQ...");
            CompletableFuture<MensajesRabbit.RespuestaIA> futuro = rabbit.enviarTarea(peticion);

            // Esperamos máximo 25 segundos (el cliente tiene timeout de 30s)
            MensajesRabbit.RespuestaIA respuesta = futuro.get(25, TimeUnit.SECONDS);

            if (respuesta.estado.equals("COMPLETADA") && respuesta.payload != null) {
                // 4. Guardar resultado en BD
                postgres.guardarResultado(idSolicitud, respuesta.payload.etiqueta, 
                                          respuesta.payload.probabilidad, respuesta.payload.duracionMs);

                // 5. Formatear para el cliente TCP original (RESULT|id|1|3|p1,p2,p3)
                List<Double> probs = respuesta.payload.probabilidades;
                return "RESULT|" + clientId + "|1|3|" + probs.get(0) + "," + probs.get(1) + "," + probs.get(2);
            } else {
                postgres.guardarSolicitud(idSolicitud, clientId, "A", "ERROR");
                return "ERROR|" + clientId + "|ia_error_" + (respuesta.error != null ? respuesta.error : "unknown");
            }

        } catch (TimeoutException e) {
            System.err.println("Timeout esperando a la IA para: " + idSolicitud);
            postgres.guardarSolicitud(idSolicitud, clientId, "A", "ERROR");
            return "ERROR|" + clientId + "|timeout_ia";
        } catch (Exception e) {
            e.printStackTrace();
            return "ERROR|" + clientId + "|server_error";
        }
    }

    private static String forward(String request) throws IOException {
        int first = Math.floorMod(cursor.getAndIncrement(), workers.size());
        IOException last = new IOException("no_worker_available");
        for (int k = 0; k < workers.size(); k++) {
            InetSocketAddress endpoint = workers.get((first + k) % workers.size()).endpoint;
            try (Socket worker = new Socket()) {
                ScheduledFuture<?> guard = closeAfter(worker, 10000);
                try {
                    worker.connect(endpoint, Math.min(2000, 10000));
                    worker.setSoTimeout(10000);
                    DataOutputStream out = new DataOutputStream(new BufferedOutputStream(worker.getOutputStream()));
                    DataInputStream in = new DataInputStream(new BufferedInputStream(worker.getInputStream()));
                    write(out, request);
                    return read(in);
                } finally { guard.cancel(false); }
            } catch (IOException ex) {
                last = ex;
                System.err.println("Worker falló: " + endpoint + " : " + ex.getMessage());
            }
        }
        throw last;
    }

    private static String validateIdentify(String[] fields) {
        if (fields.length < 2 || !validId(fields[1])) return "ERROR|unknown|invalid_request_id";
        String prefix = "ERROR|" + fields[1] + "|";
        if (fields.length != 3 && fields.length != 4) return prefix + "invalid_identify_fields";
        if (fields.length == 4 && !fields[3].equals("SEQUENTIAL") && !fields[3].equals("DISTRIBUTED"))
            return prefix + "invalid_identify_fields";
        String[] pixels = fields[2].split(",", -1);
        if (pixels.length != 256) return prefix + "invalid_image_size";
        for (String pixel : pixels) if (!normalizedNumber(pixel)) return prefix + "invalid_pixels";
        return null;
    }

    private static boolean validId(String id) {
        if (id.isEmpty() || id.codePointCount(0, id.length()) > 128) return false;
        for (int at = 0; at < id.length();) {
            int cp = id.codePointAt(at);
            if (cp == '|' || Character.isISOControl(cp) || Character.isWhitespace(cp)
                    || Character.isSpaceChar(cp) || (cp >= 0xD800 && cp <= 0xDFFF)) return false;
            at += Character.charCount(cp);
        }
        return true;
    }

    private static boolean normalizedNumber(String raw) {
        if (raw.length() > 64 || !DECIMAL.matcher(raw).matches()) return false;
        double value = Double.parseDouble(raw);
        return Double.isFinite(value) && value >= 0 && value <= 1;
    }

    private static ScheduledFuture<?> closeAfter(Socket socket, long delayMs) {
        return deadlines.schedule(() -> {
            try { socket.close(); } catch (IOException ignored) { }
        }, Math.max(1, delayMs), TimeUnit.MILLISECONDS);
    }

    private static String read(DataInputStream in) throws IOException {
        int len = in.readInt();
        if (len <= 0 || len > MAX_BYTES) throw new IOException("invalid_length");
        byte[] data = new byte[len];
        in.readFully(data);
        return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(data)).toString();
    }
    
    private static void write(DataOutputStream out, String s) throws IOException {
        byte[] data = s.getBytes(StandardCharsets.UTF_8);
        if (data.length > MAX_BYTES) throw new IOException("too_large");
        out.writeInt(data.length);
        out.write(data);
        out.flush();
    }
}