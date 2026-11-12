import com.google.gson.*;
import models.*;
import messaging.*;
import java.util.*;
import java.util.concurrent.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;

/** Phase II orchestration; never returns RESULT until persistence is confirmed. */
public final class IntegratedPipeline implements AutoCloseable {
    private final DatabaseRpc databases=new DatabaseRpc();
    private final RabbitMQManager ia;
    public IntegratedPipeline(RabbitMQManager ia)throws Exception{this.ia=ia;}
    private static String env(String k,String d){return DatabaseRpc.env(k,d);}
    private static class Run {
        final String fingerprint;final CompletableFuture<String> result=new CompletableFuture<>();
        Run(String fingerprint){this.fingerprint=fingerprint;}
    }
    private final ConcurrentHashMap<String,Run> inflight=new ConcurrentHashMap<>();
    public String process(String[] fields) {
        if(fields.length!=6 || !DatabaseMessages.id(fields[1]))return "ERROR|unknown|invalid_identify2";
        String id=fields[1], fingerprint=String.join("|",fields);
        Run own=new Run(fingerprint), previous=inflight.putIfAbsent(id,own);
        if(previous!=null) {
            if(!fingerprint.equals(previous.fingerprint))return "ERROR|"+id+"|idempotency_conflict";
            try{return previous.result.get(120,TimeUnit.SECONDS);}
            catch(InterruptedException error){Thread.currentThread().interrupt();return "ERROR|"+id+"|interrupted";}
            catch(Exception error){return "ERROR|"+id+"|request_pending";}
        }
        try{String result=processOwner(fields);own.result.complete(result);return result;}
        finally{inflight.remove(id,own);}
    }
    private String processOwner(String[] fields) {
        String id=fields.length>1&&DatabaseMessages.id(fields[1])?fields[1]:"unknown";
        String stage="validation";
        try {
            if(fields.length!=6 || !DatabaseMessages.id(fields[1]) || !DatabaseMessages.id(fields[2])
                || !Arrays.asList("SEQUENTIAL","DISTRIBUTED").contains(fields[3])
                || !Arrays.asList("image/png","image/jpeg","image/x-portable-graymap").contains(fields[4]))
                return "ERROR|"+id+"|invalid_identify2";
            byte[] bytes;
            try{bytes=Base64.getDecoder().decode(fields[5]);}catch(IllegalArgumentException error){return "ERROR|"+id+"|invalid_image";}
            if(bytes.length==0||bytes.length>1_000_000)return "ERROR|"+id+"|invalid_image";
            boolean signature = fields[4].equals("image/png") ? bytes.length>=8 && bytes[0]==(byte)137 && bytes[1]=='P' && bytes[2]=='N' && bytes[3]=='G'
                : fields[4].equals("image/jpeg") ? bytes.length>=2 && bytes[0]==(byte)255 && bytes[1]==(byte)216
                : bytes.length>=2 && bytes[0]=='P' && (bytes[1]=='2'||bytes[1]=='5');
            if(!signature)return "ERROR|"+id+"|invalid_image";
            ClientCli.PreparedImage prepared;
            Path temp=Files.createTempFile("openaicubes-image-",".bin");
            try{Files.write(temp,bytes);prepared=ClientCli.prepareImage(temp.toFile());}
            catch(Exception error){return "ERROR|"+id+"|invalid_image";}finally{Files.deleteIfExists(temp);}
            JsonObject validation=DatabaseMessages.envelope("VALIDAR_CLIENTE",id,fields[2],new JsonObject());
            JsonObject verdict=databases.call(env("QUEUE_VALIDATION","cola_validacion"),"RESULTADO_VALIDACION",validation,
                Integer.parseInt(env("VALIDATION_TIMEOUT_MS","10000")));
            if(!"VALIDADA".equals(verdict.get("estado").getAsString()))return "ERROR|"+id+"|validation_failed";
            JsonObject decision=verdict.getAsJsonObject("payload");
            if(!decision.has("aprobado")||!decision.get("aprobado").isJsonPrimitive()
                    ||!decision.get("aprobado").getAsJsonPrimitive().isBoolean())return "ERROR|"+id+"|invalid_validation_response";
            if(!decision.get("aprobado").getAsBoolean())return "ERROR|"+id+"|client_rejected";
            System.out.println("PHASE2 "+id+" VALIDADA");
            stage="inference";
            MensajesRabbit.PeticionIA request=new MensajesRabbit.PeticionIA();
            request.idSolicitud=id;request.idCliente=fields[2];request.modeloDestino="A";request.timestamp=java.time.Instant.now().toString();
            request.payload=new MensajesRabbit.PeticionIA.PayloadPeticion();request.payload.modo=fields[3];
            request.payload.imagen=new MensajesRabbit.PeticionIA.Imagen();request.payload.imagen.valores=new ArrayList<>();
            for(double x:prepared.pixels())request.payload.imagen.valores.add(x);
            MensajesRabbit.RespuestaIA response=ia.enviarTarea(request).get(ia.requestTimeoutMs()+1000L,TimeUnit.MILLISECONDS);
            if(!"COMPLETADA".equals(response.estado)||response.payload==null)return "ERROR|"+id+"|inference_failed";
            JsonObject payload=new Gson().toJsonTree(response.payload).getAsJsonObject();
            JsonObject image=new JsonObject();image.addProperty("sha256",HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes)));
            image.addProperty("nombre",id);image.addProperty("mimeType",fields[4]);
            image.addProperty("ancho",prepared.width);image.addProperty("alto",prepared.height);payload.add("imagen",image);
            JsonObject persist=DatabaseMessages.envelope("GUARDAR_RESULTADO",id,fields[2],payload);DatabaseMessages.persistence(persist);
            System.out.println("PHASE2 "+id+" CLASIFICADA");
            stage="persistence";
            JsonObject confirmation=databases.call(env("QUEUE_PERSISTENCE","cola_persistencia"),"RESULTADO_PERSISTENCIA",persist,
                Integer.parseInt(env("PERSISTENCE_TIMEOUT_MS","10000")));
            if(!"PERSISTIDA".equals(confirmation.get("estado").getAsString()))return "ERROR|"+id+"|persistence_failed";
            System.out.println("PHASE2 "+id+" PERSISTIDA");
            List<Double> p=response.payload.probabilidades;
            return "RESULT|"+id+"|1|3|"+p.get(0)+","+p.get(1)+","+p.get(2);
        }catch(TimeoutException error){return "ERROR|"+id+"|"+(stage.equals("persistence")?"persistence_pending":stage+"_timeout");}
        catch(ExecutionException error){return "ERROR|"+id+"|"+(error.getCause() instanceof TimeoutException?(stage.equals("persistence")?"persistence_pending":stage+"_timeout"):stage+"_failed");}
        catch(InterruptedException error){Thread.currentThread().interrupt();return "ERROR|"+id+"|interrupted";}
        catch(Exception error){return "ERROR|"+id+"|"+stage+"_failed";}
    }
    public void close()throws Exception{databases.close();}
}
