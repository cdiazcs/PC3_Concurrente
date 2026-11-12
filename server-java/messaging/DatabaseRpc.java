package messaging;
import com.rabbitmq.client.*;
import com.google.gson.*;
import models.DatabaseMessages;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.*;

public final class DatabaseRpc implements AutoCloseable {
    public static String env(String key,String fallback){return System.getenv().getOrDefault(key,fallback);}
    public static ConnectionFactory factory() {
        ConnectionFactory f=new ConnectionFactory();f.setHost(env("RABBITMQ_HOST","127.0.0.1"));
        f.setPort(Integer.parseInt(env("RABBITMQ_PORT","5672")));f.setVirtualHost(env("RABBITMQ_VHOST","/"));
        String user=env("RABBITMQ_USER",""),password=env("RABBITMQ_PASSWORD","");
        if(user.isEmpty()||password.isEmpty())throw new IllegalArgumentException("rabbit_credentials_required");
        f.setUsername(user);f.setPassword(password);f.setConnectionTimeout(5000);f.setRequestedHeartbeat(60);
        return f;
    }
    private static class Pending {
        final String client,kind;final CompletableFuture<JsonObject> future=new CompletableFuture<>();
        Pending(String c,String k){client=c;kind=k;}
    }
    private final Connection connection;
    private final Channel publisher,consumer;
    private final ConcurrentHashMap<String,Pending> pending=new ConcurrentHashMap<>();
    public DatabaseRpc() throws Exception {
        connection=factory().newConnection();
        try {
            publisher=connection.createChannel();consumer=connection.createChannel();publisher.confirmSelect();consumer.basicQos(64);
            listen(env("QUEUE_VALIDATION_RESULTS","cola_resultados_validacion"),"RESULTADO_VALIDACION");
            listen(env("QUEUE_PERSISTENCE_RESULTS","cola_resultados_bd"),"RESULTADO_PERSISTENCIA");
        } catch(Exception e){connection.close();throw e;}
    }
    private void listen(String queue,String kind)throws Exception {
        consumer.queueDeclare(queue,true,false,false,null);
        consumer.basicConsume(queue,false,(tag,delivery)->{
            try {
                JsonObject value=JsonParser.parseString(new String(delivery.getBody(),StandardCharsets.UTF_8)).getAsJsonObject();
                DatabaseMessages.validate(value,kind,delivery.getProperties().getCorrelationId());
                Pending item=pending.get(kind+":"+value.get("idSolicitud").getAsString());
                if(item!=null && item.client.equals(value.get("idCliente").getAsString()))item.future.complete(value);
                consumer.basicAck(delivery.getEnvelope().getDeliveryTag(),false);
            }catch(RuntimeException invalid){consumer.basicReject(delivery.getEnvelope().getDeliveryTag(),false);}
        },tag->{});
    }
    public JsonObject call(String queue,String responseType,JsonObject value,int timeoutMs)throws Exception {
        String id=value.get("idSolicitud").getAsString(), key=responseType+":"+id;
        Pending item=new Pending(value.get("idCliente").getAsString(),responseType);
        if(pending.putIfAbsent(key,item)!=null)throw new IllegalArgumentException("duplicate_request_in_flight");
        try {
            synchronized(publisher) {
                publisher.queueDeclare(queue,true,false,false,null);
                publisher.basicPublish("",queue,new AMQP.BasicProperties.Builder().contentType("application/json")
                    .deliveryMode(2).correlationId(id).messageId(id).build(),value.toString().getBytes(StandardCharsets.UTF_8));
                publisher.waitForConfirmsOrDie(5000);
            }
            return item.future.get(timeoutMs,TimeUnit.MILLISECONDS);
        } finally {pending.remove(key,item);}
    }
    public void close()throws Exception{pending.values().forEach(p->p.future.cancel(false));pending.clear();connection.close();}
}
