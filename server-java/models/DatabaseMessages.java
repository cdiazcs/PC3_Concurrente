package models;
import com.google.gson.*;
import java.util.*;

public final class DatabaseMessages {
    public static boolean id(String value) {
        return value != null && value.matches("[A-Za-z0-9_.:-]{1,128}");
    }
    public static JsonObject envelope(String type,String id,String client,JsonObject payload) {
        JsonObject value=new JsonObject();value.addProperty("schemaVersion",1);
        value.addProperty("tipo",type);value.addProperty("idSolicitud",id);value.addProperty("idCliente",client);
        value.addProperty("modeloDestino","A");value.addProperty("timestamp",java.time.Instant.now().toString());
        value.add("payload",payload);return value;
    }
    public static void validate(JsonObject value,String kind,String correlation) {
        if(value==null || !value.has("schemaVersion") || !"1".equals(value.get("schemaVersion").toString())
            || !kind.equals(value.get("tipo").getAsString()) || !"A".equals(value.get("modeloDestino").getAsString())
            || !id(value.get("idSolicitud").getAsString()) || !id(value.get("idCliente").getAsString())
            || !value.get("idSolicitud").getAsString().equals(correlation) || !value.get("payload").isJsonObject())
            throw new IllegalArgumentException("invalid_database_message");
        java.time.Instant.parse(value.get("timestamp").getAsString());
    }
    public static JsonElement canonical(JsonElement value) {
        if(value.isJsonObject()) {
            JsonObject sorted=new JsonObject();
            for(String key:new TreeSet<>(value.getAsJsonObject().keySet()))sorted.add(key,canonical(value.getAsJsonObject().get(key)));
            return sorted;
        }
        if(value.isJsonArray()) {
            JsonArray array=new JsonArray();for(JsonElement item:value.getAsJsonArray())array.add(canonical(item));return array;
        }
        if(value.isJsonPrimitive()&&value.getAsJsonPrimitive().isNumber())
            return new JsonPrimitive(value.getAsBigDecimal().stripTrailingZeros());
        return value;
    }
    public static void persistence(JsonObject value) {
        JsonObject p=value.getAsJsonObject("payload"), image=p.getAsJsonObject("imagen");
        if(!image.get("sha256").getAsString().matches("[0-9a-f]{64}")
            || image.get("nombre").getAsString().length()>255
            || !Arrays.asList("image/png","image/jpeg","image/x-portable-graymap").contains(image.get("mimeType").getAsString()))
            throw new IllegalArgumentException("invalid_image_metadata");
        JsonArray probabilities=p.getAsJsonArray("probabilidades");
        if(probabilities.size()!=3) throw new IllegalArgumentException("invalid_probabilities");
        double sum=0;int best=0;
        for(int i=0;i<3;i++) {
            double x=probabilities.get(i).getAsDouble();
            if(!Double.isFinite(x)||x<0||x>1) throw new IllegalArgumentException("invalid_probabilities");
            sum+=x;if(x>probabilities.get(best).getAsDouble())best=i;
        }
        double ms=p.get("duracionMs").getAsDouble();
        if(Math.abs(sum-1)>1e-8 || !Double.isFinite(ms) || ms<0
            || !Arrays.asList("circulo","cruz","triangulo").get(best).equals(p.get("etiqueta").getAsString())
            || Math.abs(probabilities.get(best).getAsDouble()-p.get("probabilidad").getAsDouble())>1e-8)
            throw new IllegalArgumentException("invalid_classification");
    }
}
