import models.DatabaseMessages;
import com.google.gson.*;
public class DatabaseContractChecks {
    public static void main(String[] args) {
        JsonObject payload=JsonParser.parseString("{\"etiqueta\":\"circulo\",\"probabilidad\":0.8,\"probabilidades\":[0.8,0.1,0.1],\"duracionMs\":1,\"imagen\":{\"nombre\":\"test\",\"mimeType\":\"image/png\",\"sha256\":\""+"a".repeat(64)+"\"}}").getAsJsonObject();
        JsonObject request=DatabaseMessages.envelope("GUARDAR_RESULTADO","db-1","cliente-demo-01",payload);
        DatabaseMessages.validate(request,"GUARDAR_RESULTADO","db-1");DatabaseMessages.persistence(request);
        for(int mode=0;mode<4;mode++) {
            JsonObject invalid=request.deepCopy();
            if(mode==0)invalid.addProperty("schemaVersion",2);
            if(mode==1)invalid.getAsJsonObject("payload").addProperty("etiqueta","cruz");
            if(mode==2)invalid.getAsJsonObject("payload").getAsJsonArray("probabilidades").set(0,new JsonPrimitive(-0.8));
            try {
                DatabaseMessages.validate(invalid,"GUARDAR_RESULTADO",mode==3?"another-id":"db-1");DatabaseMessages.persistence(invalid);
                throw new AssertionError("accepted invalid contract");
            }catch(IllegalArgumentException|IllegalStateException expected){}
        }
        System.out.println("OK: contratos BD Java, schema, correlacion, etiqueta y probabilidades");
    }
}
