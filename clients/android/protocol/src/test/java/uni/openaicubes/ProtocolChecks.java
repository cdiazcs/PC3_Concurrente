package uni.openaicubes;
import java.io.*;
public class ProtocolChecks {
    public static void main(String[] args)throws Exception {
        String request=Protocol.request("android-1","cliente-android-01","SEQUENTIAL","image/png",new byte[]{1,2,3});
        if(!request.equals("IDENTIFY2|android-1|cliente-android-01|SEQUENTIAL|image/png|AQID"))throw new AssertionError(request);
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();Protocol.write(new DataOutputStream(bytes),request);
        if(!request.equals(Protocol.read(new DataInputStream(new ByteArrayInputStream(bytes.toByteArray())))))throw new AssertionError("frame");
        if(!Protocol.result("RESULT|android-1|1|3|0.8,0.1,0.1","android-1").label.equals("circulo"))throw new AssertionError("result");
        for(String invalid:new String[]{"RESULT|other|1|3|0.8,0.1,0.1","RESULT|android-1|1|3|NaN,0,1","RESULT|android-1|1|3|0.1,0.1,0.1","ERROR|android-1|client_rejected"}){
            try{Protocol.result(invalid,"android-1");throw new AssertionError("accepted invalid response");}catch(IOException expected){}
        }
        try{Protocol.request("id","bad|id","SEQUENTIAL","image/png",new byte[]{1});throw new AssertionError("ID");}catch(IllegalArgumentException expected){}
        System.out.println("OK: contrato Android JVM, framing, IDs, errores y probabilidades");
    }
}
