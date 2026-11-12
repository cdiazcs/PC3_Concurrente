package db;
import messaging.DatabaseRpc;
import models.DatabaseMessages;
import com.rabbitmq.client.*;
import com.google.gson.*;
import java.nio.charset.StandardCharsets;
import java.sql.SQLException;
import java.util.*;
import java.util.concurrent.CountDownLatch;

/** ACK follows SQL commit and confirmed publication; durable request drives outbox replay. */
public final class PersistenceWorker {
    private static String env(String k,String d){return DatabaseRpc.env(k,d);}
    private static void publish(Channel channel,String queue,JsonObject result,String id,Map<String,Object> headers)throws Exception{
        channel.basicPublish("",queue,new AMQP.BasicProperties.Builder().contentType("application/json")
            .deliveryMode(2).correlationId(id).messageId(id).headers(headers).build(),result.toString().getBytes(StandardCharsets.UTF_8));
        channel.waitForConfirmsOrDie(5000);
    }
    public static void main(String[] args)throws Exception {
        String input=env("QUEUE_PERSISTENCE","cola_persistencia"),output=env("QUEUE_PERSISTENCE_RESULTS","cola_resultados_bd"),errors=input+".errores";
        PostgresManager db=new PostgresManager(env("POSTGRES_HOST","127.0.0.1"),Integer.parseInt(env("POSTGRES_PORT","5432")),
            env("POSTGRES_DB","pc3_concurrente"),env("POSTGRES_USER",""),env("POSTGRES_PASSWORD",""));
        if(env("POSTGRES_USER","").isEmpty()||env("POSTGRES_PASSWORD","").isEmpty())throw new IllegalArgumentException("postgres_credentials_required");
        Connection connection=DatabaseRpc.factory().newConnection();
        Channel channel=connection.createChannel();
        for(String queue:Arrays.asList(input,output,errors))channel.queueDeclare(queue,true,false,false,null);
        channel.confirmSelect();channel.basicQos(1);
        Runtime.getRuntime().addShutdownHook(new Thread(()->{try{connection.close();}catch(Exception ignored){}}));
        channel.basicConsume(input,false,(tag,delivery)->{
            JsonObject value=null;String id=delivery.getProperties().getCorrelationId();
            try {
                if(delivery.getBody().length>2_000_000)throw new IllegalArgumentException("message_size");
                value=JsonParser.parseString(new String(delivery.getBody(),StandardCharsets.UTF_8)).getAsJsonObject();
                DatabaseMessages.validate(value,"GUARDAR_RESULTADO",id);DatabaseMessages.persistence(value);
                JsonObject result=db.persistir(value);
                System.out.println("DB_COMMIT "+id);
                publish(channel,output,result,id,null);
                System.out.println("PERSISTIDA "+id);
                channel.basicAck(delivery.getEnvelope().getDeliveryTag(),false);
            } catch(Exception failure) {
                try {
                    if(failure instanceof java.io.IOException || failure instanceof java.util.concurrent.TimeoutException) {
                        // Unconfirmed publication: retain input for broker redelivery, including after SQL COMMIT.
                        connection.abort();return;
                    }
                    String code=failure instanceof SQLException?"persistence_failed":"invalid_persistence_message";
                    if(failure instanceof SQLException && "23505".equals(((SQLException)failure).getSQLState()))code="idempotency_conflict";
                    int attempt=1;
                    Object raw=delivery.getProperties().getHeaders()==null?null:delivery.getProperties().getHeaders().get("x-db-attempt");
                    if(raw instanceof Number)attempt=((Number)raw).intValue();
                    if(attempt<1||attempt>3)attempt=3;
                    if(failure instanceof SQLException && ((SQLException)failure).getSQLState()!=null
                            && (((SQLException)failure).getSQLState().startsWith("08") || ((SQLException)failure).getSQLState().startsWith("40")) && attempt<3 && value!=null) {
                        publish(channel,input,value,id,Collections.singletonMap("x-db-attempt",attempt+1));
                    } else {
                        String client="unknown";
                        if(value!=null && value.has("idCliente") && value.get("idCliente").isJsonPrimitive()
                                && value.get("idCliente").getAsJsonPrimitive().isString()
                                && DatabaseMessages.id(value.get("idCliente").getAsString()))client=value.get("idCliente").getAsString();
                        JsonObject result=DatabaseMessages.envelope("RESULTADO_PERSISTENCIA",DatabaseMessages.id(id)?id:"unknown",client,new JsonObject());
                        result.addProperty("estado","ERROR");result.addProperty("error",code);
                        if(DatabaseMessages.id(id))publish(channel,output,result,id,null);
                        publish(channel,errors,result,id,null);
                    }
                    channel.basicAck(delivery.getEnvelope().getDeliveryTag(),false);
                }catch(Exception publicationFailure){connection.abort();}
            }
        },tag->{});
        System.out.println("PersistenceWorker listo: "+input);
        while(connection.isOpen())Thread.sleep(200);
        throw new IllegalStateException("persistence_connection_closed_restart_worker");
    }
}
