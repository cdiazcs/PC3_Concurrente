import db.PostgresManager;
import com.google.gson.*;
import java.nio.file.*;
public class PostgresTransactionChecks {
    public static void main(String[] args)throws Exception {
        PostgresManager db=new PostgresManager(System.getenv("POSTGRES_HOST"),Integer.parseInt(System.getenv("POSTGRES_PORT")),
            System.getenv("POSTGRES_DB"),System.getenv("POSTGRES_USER"),System.getenv("POSTGRES_PASSWORD"));
        JsonObject value=JsonParser.parseString(Files.readString(Path.of(args[0]))).getAsJsonObject();
        models.DatabaseMessages.persistence(value);
        System.out.println(db.persistir(value));
    }
}
