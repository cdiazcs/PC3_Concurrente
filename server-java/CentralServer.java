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
    private static final int WORKER_TIMEOUT_MS = timeout("worker", 10000);
    private static final int IDENTIFY_TIMEOUT_MS = timeout("identify", 12000);
    private static final int CLIENT_TIMEOUT_MS = timeout("client", 30000);
    private static final Pattern DECIMAL = Pattern.compile("[+-]?(?:[0-9]+(?:\\.[0-9]*)?|\\.[0-9]+)(?:[eE][+-]?[0-9]+)?");
    private static final AtomicInteger cursor = new AtomicInteger();
    private static final List<Node> workers = new ArrayList<>();
    private static DistributedCnn distributed;

    // NUEVOS GESTORES
    private static IntegratedPipeline pipeline;
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
        if (args.length == 0) args = new String[] {env("BACKEND_PORT", "9000"),
            env("WORKER_JAVA_HOST", "127.0.0.1")+":"+env("WORKER_JAVA_PORT", "9101"),
            env("WORKER_PYTHON_HOST", "127.0.0.1")+":"+env("WORKER_PYTHON_PORT", "9102"),
            env("WORKER_CSHARP_HOST", "127.0.0.1")+":"+env("WORKER_CSHARP_PORT", "9103")};
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
        distributed = new DistributedCnn(endpoints, WORKER_TIMEOUT_MS, IDENTIFY_TIMEOUT_MS);

        String pipelineMode=env("SYSTEM_PIPELINE","LEGACY");
        if(!pipelineMode.equals("FULL")&&!pipelineMode.equals("LEGACY"))throw new IllegalArgumentException("invalid_system_pipeline");
        if(pipelineMode.equals("FULL")) {
            long validation=Long.parseLong(env("VALIDATION_TIMEOUT_MS","10000"));
            long persistence=Long.parseLong(env("PERSISTENCE_TIMEOUT_MS","10000"));
            long inference=Long.parseLong(env("RABBITMQ_REQUEST_TIMEOUT_MS","25000"));
            if(!env("INFERENCE_TRANSPORT","TCP").equals("RABBITMQ") || validation<1 || validation>60000
                || persistence<1 || persistence>60000 || CLIENT_TIMEOUT_MS<=validation+persistence+inference+5000)
                throw new IllegalArgumentException("full_pipeline_requires_rabbit_and_larger_client_timeout");
        }
        if (!env("SYSTEM_PIPELINE","LEGACY").equals("FULL") && Boolean.parseBoolean(env("POSTGRES_ENABLED", "false"))) {
            postgres = new PostgresManager(env("POSTGRES_HOST", "127.0.0.1"),
                Integer.parseInt(env("POSTGRES_PORT", "5432")), env("POSTGRES_DB", "pc3_concurrente"),
                env("POSTGRES_USER", ""), env("POSTGRES_PASSWORD", ""));
        }
        if (env("INFERENCE_TRANSPORT", "TCP").equals("RABBITMQ")) {
            int requestTimeout = Integer.parseInt(env("RABBITMQ_REQUEST_TIMEOUT_MS", "25000"));
            if (CLIENT_TIMEOUT_MS <= requestTimeout + 1000L)
                throw new IllegalArgumentException("backend_client_timeout_must_exceed_rabbit_request_timeout");
            rabbit = new RabbitMQManager(env("RABBITMQ_HOST", "127.0.0.1"),
                Integer.parseInt(env("RABBITMQ_PORT", "5672")));
        } else if (!env("INFERENCE_TRANSPORT", "TCP").equals("TCP")) {
            throw new IllegalArgumentException("invalid_inference_transport");
        }

        if (env("SYSTEM_PIPELINE","LEGACY").equals("FULL")) {
            int total=Integer.parseInt(env("VALIDATION_TIMEOUT_MS","10000"))+Integer.parseInt(env("PERSISTENCE_TIMEOUT_MS","10000"));
            if(rabbit==null || CLIENT_TIMEOUT_MS <= total+rabbit.requestTimeoutMs()+5000)
                throw new IllegalArgumentException("full_pipeline_requires_rabbit_and_larger_client_timeout");
            try{pipeline=new IntegratedPipeline(rabbit);}
            catch(Exception startupFailure){rabbit.close();distributed.close();throw startupFailure;}
        } else if(!env("SYSTEM_PIPELINE","LEGACY").equals("LEGACY"))throw new IllegalArgumentException("invalid_system_pipeline");
        int maxClients = Integer.getInteger("openaicubes.maxClients", Integer.parseInt(env("BACKEND_MAX_CLIENTS", "64")));
        if (maxClients < 1 || maxClients > 1024) throw new IllegalArgumentException("invalid_max_clients");

        ExecutorService clients = new ThreadPoolExecutor(Math.min(16, maxClients), maxClients,
            30, TimeUnit.SECONDS, new SynchronousQueue<Runnable>());
        try (ServerSocket listener = new ServerSocket(port, 50, InetAddress.getByName(env("BACKEND_BIND_HOST", "127.0.0.1")))) {
            System.out.println("CentralServer en " + port + ", workers=" + workers);
            while (true) {
                Socket socket = listener.accept();
                try { clients.execute(() -> handle(socket)); }
                catch (RejectedExecutionException busy) {
                    socket.close();
                    System.err.println("Conexion rechazada: client_limit");
                }
            }
        } finally { if(pipeline!=null)pipeline.close(); if (rabbit != null) rabbit.close(); clients.shutdown(); distributed.close(); deadlines.shutdownNow(); }
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
                    } else if (fields[0].equals("IDENTIFY2")) {
                        reply=pipeline==null?"ERROR|"+id+"|full_pipeline_required":pipeline.process(fields);
                    } else if (fields[0].equals("IDENTIFY") && pipeline!=null) {
                        reply="ERROR|"+id+"|client_identity_required";
                    } else if (fields[0].equals("IDENTIFY")) {
                        String invalid = validateIdentify(fields);
                        if (invalid != null) {
                            reply = invalid;
                        } else {
                            // Mantener separados el transporte AMQP y el coordinador de operaciones.
                            if (fields.length == 4 && fields[3].equals("DISTRIBUTED")) {
                                try { reply = distributed.identify(id, fields[2]); }
                                catch (DistributedCnn.Failure failure) { reply = "ERROR|"+id+"|"+failure.code; }
                            } else if (rabbit != null) reply = procesarConRabbitMQ(id, fields[2]);
                            else reply = identify("IDENTIFY|"+id+"|"+fields[2], id);
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
        String idSolicitud = clientId;
        try {
            // 1. Guardar en BD (RECIBIDA)
            if (postgres != null) postgres.guardarSolicitud(idSolicitud, clientId, "A", "RECIBIDA");

            // 2. Preparar el JSON para RabbitMQ
            MensajesRabbit.PeticionIA peticion = new MensajesRabbit.PeticionIA();
            peticion.idSolicitud = idSolicitud;
            peticion.idCliente = clientId;
            peticion.modeloDestino = "A";
            peticion.payload = new MensajesRabbit.PeticionIA.PayloadPeticion();
            peticion.payload.modo = "SEQUENTIAL";
            peticion.payload.imagen = new MensajesRabbit.PeticionIA.Imagen();
            peticion.payload.imagen.valores = Arrays.stream(pixels.split(",")).map(Double::valueOf)
                .collect(java.util.stream.Collectors.toList());
            peticion.timestamp = java.time.Instant.now().toString();

            // 3. Enviar a RabbitMQ y esperar respuesta
            System.out.println("Enviando tarea " + idSolicitud + " a RabbitMQ...");
            CompletableFuture<MensajesRabbit.RespuestaIA> futuro = rabbit.enviarTarea(peticion);

            // El futuro vence antes del deadline de la conexion TCP.
            MensajesRabbit.RespuestaIA respuesta = futuro.get(rabbit.requestTimeoutMs() + 1000L, TimeUnit.MILLISECONDS);

            if ("COMPLETADA".equals(respuesta.estado) && respuesta.payload != null) {
                // 4. Guardar resultado en BD
                if (postgres != null) postgres.guardarResultado(idSolicitud, respuesta.payload.etiqueta,
                                          respuesta.payload.probabilidad, respuesta.payload.duracionMs);

                // 5. Formatear para el cliente TCP original (RESULT|id|1|3|p1,p2,p3)
                List<Double> probs = respuesta.payload.probabilidades;
                if (probs == null || probs.size() != 3) throw new InvalidWorkerResponse();
                String result = "RESULT|" + clientId + "|1|3|" + probs.get(0) + "," + probs.get(1) + "," + probs.get(2);
                validateIdentifyReply(result, clientId);
                return result;
            } else {
                if (postgres != null) postgres.guardarSolicitud(idSolicitud, clientId, "A", "ERROR");
                return "ERROR|" + clientId + "|ia_error_" + (respuesta.error != null && respuesta.error.matches("[A-Za-z0-9_:-]{1,100}") ? respuesta.error : "unknown");
            }

        } catch (TimeoutException e) {
            System.err.println("Timeout esperando a la IA para: " + idSolicitud);
            return "ERROR|" + clientId + "|timeout_ia";
        } catch (ExecutionException e) {
            return "ERROR|" + clientId + (e.getCause() instanceof TimeoutException ? "|timeout_ia" : "|server_error");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return "ERROR|" + clientId + "|server_interrupted";
        } catch (Exception e) {
            e.printStackTrace();
            return "ERROR|" + clientId + "|server_error";
        }
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return value == null ? fallback : value;
    }

    private static String identify(String request, String id) {
        long end = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(IDENTIFY_TIMEOUT_MS);
        String failure = "no_identify_worker_available";
        for (Node node : workers) {
            if (node.skipIdentifyUntil != 0 && node.skipIdentifyUntil - System.nanoTime() > 0) continue;
            long remaining = TimeUnit.NANOSECONDS.toMillis(end - System.nanoTime());
            if (remaining <= 0) return "ERROR|" + id + "|identify_worker_timeout";
            int attemptMs = (int)Math.min(remaining, WORKER_TIMEOUT_MS);
            long attemptEnd = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(attemptMs);
            try (Socket worker = new Socket()) {
                ScheduledFuture<?> guard = closeAfter(worker, attemptMs);
                try {
                    worker.connect(node.endpoint, Math.min(2000, attemptMs));
                    worker.setSoTimeout(Math.min(2000, attemptMs));
                    DataOutputStream out = new DataOutputStream(new BufferedOutputStream(worker.getOutputStream()));
                    DataInputStream in = new DataInputStream(new BufferedInputStream(worker.getInputStream()));
                    // PING en la misma conexion evita usar una capacidad antigua tras un reinicio.
                    write(out, "PING|" + id);
                    String[] pong = read(in).split("\\|", -1);
                    if (pong.length != 3 || !pong[0].equals("PONG") || !pong[1].equals(id))
                        throw new InvalidWorkerResponse();
                    if (!pong[2].equals("Python")) {
                        node.skipIdentifyUntil = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                        continue;
                    }
                    worker.setSoTimeout(attemptMs);
                    write(out, request);
                    String reply = read(in);
                    validateIdentifyReply(reply, id);
                    if (reply.equals("ERROR|" + id + "|unsupported_command")) {
                        node.skipIdentifyUntil = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
                        continue;
                    }
                    return reply;
                } finally { guard.cancel(false); }
            } catch (InvalidWorkerResponse ex) {
                failure = "invalid_worker_response";
            } catch (SocketTimeoutException ex) {
                failure = "identify_worker_timeout";
            } catch (IOException ex) {
                if (System.nanoTime() - attemptEnd >= 0) failure = "identify_worker_timeout";
                System.err.println("IDENTIFY worker fallo: " + node.endpoint + " : " + ex.getMessage());
            }
        }
        return "ERROR|" + id + "|" + failure;
    }

    private static void validateIdentifyReply(String reply, String id) throws IOException {
        String[] fields = reply.split("\\|", -1);
        if (fields.length == 3 && fields[0].equals("ERROR") && fields[1].equals(id)
                && fields[2].matches("[A-Za-z0-9_:-]{1,128}")) return;
        if (fields.length != 5 || !fields[0].equals("RESULT") || !fields[1].equals(id)
                || !fields[2].equals("1") || !fields[3].equals("3")) throw new InvalidWorkerResponse();
        String[] values = fields[4].split(",", -1);
        if (values.length != 3) throw new InvalidWorkerResponse();
        double sum = 0;
        for (String value : values) {
            if (!normalizedNumber(value)) throw new InvalidWorkerResponse();
            sum += Double.parseDouble(value);
        }
        if (Math.abs(sum - 1) > 1e-8) throw new InvalidWorkerResponse();
    }

    private static int timeout(String name, int fallback) {
        String raw = env("BACKEND_" + name.toUpperCase(Locale.ROOT) + "_TIMEOUT_MS", Integer.toString(fallback));
        int value = Integer.getInteger("openaicubes." + name + "TimeoutMs", Integer.parseInt(raw));
        if (value < 1 || value > 120000) throw new IllegalArgumentException("invalid_timeout");
        return value;
    }

    private static String forward(String request) throws IOException {
        int first = Math.floorMod(cursor.getAndIncrement(), workers.size());
        IOException last = new IOException("no_worker_available");
        for (int k = 0; k < workers.size(); k++) {
            InetSocketAddress endpoint = workers.get((first + k) % workers.size()).endpoint;
            try (Socket worker = new Socket()) {
                ScheduledFuture<?> guard = closeAfter(worker, WORKER_TIMEOUT_MS);
                try {
                    worker.connect(endpoint, Math.min(2000, WORKER_TIMEOUT_MS));
                    worker.setSoTimeout(WORKER_TIMEOUT_MS);
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
