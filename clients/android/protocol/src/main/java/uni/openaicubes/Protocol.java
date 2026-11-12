package uni.openaicubes;
import java.io.*;
import java.nio.*;
import java.nio.charset.*;
import java.util.*;

/** Pure JVM protocol, shared by the Android Activity and executable contract tests. */
public final class Protocol {
    public static final int MAX_BYTES=2_000_000;
    public static boolean validId(String id){return id!=null&&id.matches("[A-Za-z0-9_.:-]{1,128}");}
    public static String request(String id,String client,String mode,String mime,byte[] image) {
        if(!validId(id)||!validId(client)||!Arrays.asList("SEQUENTIAL","DISTRIBUTED").contains(mode)
            ||!Arrays.asList("image/png","image/jpeg","image/x-portable-graymap").contains(mime)
            ||image==null||image.length==0||image.length>1_000_000)throw new IllegalArgumentException("invalid_request");
        return "IDENTIFY2|"+id+"|"+client+"|"+mode+"|"+mime+"|"+Base64.getEncoder().encodeToString(image);
    }
    public static void write(DataOutputStream out,String value)throws IOException {
        byte[] bytes=value.getBytes(StandardCharsets.UTF_8);
        if(bytes.length==0||bytes.length>MAX_BYTES)throw new IOException("invalid_frame");
        out.writeInt(bytes.length);out.write(bytes);out.flush();
    }
    public static String read(DataInputStream in)throws IOException {
        int length=in.readInt();if(length<1||length>MAX_BYTES)throw new IOException("invalid_frame");
        byte[] bytes=new byte[length];in.readFully(bytes);
        return StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(bytes)).toString();
    }
    public static final class Result {
        public final String label;public final double probability;
        Result(String name,double confidence){label=name;probability=confidence;}
    }
    public static Result result(String text,String id)throws IOException {
        String[] f=text.split("\\|",-1);
        if(f.length==3&&f[0].equals("ERROR")&&f[1].equals(id)&&f[2].matches("[A-Za-z0-9_:-]{1,128}"))throw new IOException(f[2]);
        if(f.length!=5||!Arrays.equals(Arrays.copyOf(f,4),new String[]{"RESULT",id,"1","3"}))throw new IOException("invalid_response_id");
        String[] raw=f[4].split(",",-1);if(raw.length!=3)throw new IOException("invalid_probabilities");
        double[] p=new double[3];double sum=0;int best=0;
        try{for(int i=0;i<3;i++){p[i]=Double.parseDouble(raw[i]);if(!Double.isFinite(p[i])||p[i]<0||p[i]>1)throw new IOException("invalid_probabilities");sum+=p[i];if(p[i]>p[best])best=i;}}
        catch(NumberFormatException e){throw new IOException("invalid_probabilities");}
        if(Math.abs(sum-1)>1e-8)throw new IOException("invalid_probabilities");
        return new Result(new String[]{"circulo","cruz","triangulo"}[best],p[best]);
    }
}
