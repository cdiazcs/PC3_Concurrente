import java.net.*;
import java.io.*;
import java.nio.file.*;
import uni.openaicubes.Protocol;
public class Phase2Clients {
    public static void main(String[] args)throws Exception {
        String type=args[0],host=args[1],id=args[3],client=args[4];int port=Integer.parseInt(args[2]);
        if(type.equals("desktop-ui")) {
            java.util.concurrent.atomic.AtomicReference<OpenAICubesPanel> view=new java.util.concurrent.atomic.AtomicReference<>();
            javax.swing.SwingUtilities.invokeAndWait(()->{
                OpenAICubesPanel panel=new OpenAICubesPanel(host,port,new ImageClient.Identity());
                panel.clientId.setText(client);panel.mode.setSelectedItem(ImageClient.Mode.SEQUENTIAL);
                view.set(panel);panel.loadFile(new File(args[5]));
            });
            OpenAICubesPanel panel=view.get();
            try {
                long end=System.nanoTime()+java.util.concurrent.TimeUnit.SECONDS.toNanos(30);
                java.util.concurrent.atomic.AtomicBoolean ready=new java.util.concurrent.atomic.AtomicBoolean();
                while(!ready.get() && System.nanoTime()<end){javax.swing.SwingUtilities.invokeAndWait(()->ready.set(panel.selected!=null&&!panel.loading));Thread.sleep(20);}
                if(!ready.get())throw new AssertionError("UI image timeout");
                javax.swing.SwingUtilities.invokeAndWait(()->panel.send.doClick(0));ready.set(false);
                while(!ready.get() && System.nanoTime()<end){javax.swing.SwingUtilities.invokeAndWait(()->ready.set(panel.active.isEmpty()));Thread.sleep(20);}
                javax.swing.SwingUtilities.invokeAndWait(()->{
                    if(!panel.active.isEmpty()||panel.chat.entries.size()!=1)throw new AssertionError("UI response timeout");
                    ChatPanel.Entry entry=panel.chat.entries.get(0);
                    if(entry.response==null || entry.error!=null)throw new AssertionError("UI error: "+entry.error);
                    System.out.println(entry.requestId+" "+entry.response.prediction.label());
                });
            } finally {javax.swing.SwingUtilities.invokeAndWait(panel::close);}
        } else if(type.equals("desktop")) {
            try(ImageClient connection=new ImageClient(host,port,80000)) {
                ImageClient.Response result=connection.identifyImage(id,client,ClientCli.prepareImage(new File(args[5])),ImageClient.Mode.SEQUENTIAL,phase->{});
                System.out.println(result.requestId+" "+result.prediction.label());
            }
        } else {
            try(Socket socket=new Socket(host,port)) {
                socket.setSoTimeout(80000);
                Protocol.write(new DataOutputStream(socket.getOutputStream()),Protocol.request(id,client,"SEQUENTIAL","image/png",Files.readAllBytes(Path.of(args[5]))));
                Protocol.Result result=Protocol.result(Protocol.read(new DataInputStream(socket.getInputStream())),id);
                System.out.println(id+" "+result.label);
            }
        }
    }
}
