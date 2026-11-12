package db;

import java.sql.*;

public class PostgresManager {
    private final String url;
    private final String user;
    private final String password;

    public PostgresManager(String host, int port, String dbName, String user, String password) {
        this.url = "jdbc:postgresql://" + host + ":" + port + "/" + dbName;
        this.user = user;
        this.password = password;
    }

    private Connection open() throws SQLException {
        java.util.Properties properties = new java.util.Properties();
        properties.setProperty("user", user);
        properties.setProperty("password", password);
        properties.setProperty("connectTimeout", "5");
        properties.setProperty("socketTimeout", "10");
        return DriverManager.getConnection(url, properties);
    }

    public void guardarSolicitud(String id, String cliente, String modelo, String estado) throws SQLException {
        try (Connection connection = open(); PreparedStatement statement = connection.prepareStatement(
                "INSERT INTO solicitudes(id_solicitud,id_cliente,modelo,estado) VALUES(?,?,?,?) ON CONFLICT DO NOTHING")) {
            statement.setString(1,id); statement.setString(2,cliente); statement.setString(3,modelo);
            statement.setString(4,estado); statement.executeUpdate();
        }
    }

    public void guardarResultado(String id, String etiqueta, double probabilidad, double duracionMs) throws SQLException {
        try (Connection connection = open()) {
            connection.setAutoCommit(false);
            try {
                try (PreparedStatement statement = connection.prepareStatement(
                        "INSERT INTO clasificaciones(id_solicitud,etiqueta,probabilidad,duracion_ms) VALUES(?,?,?,?)")) {
                    statement.setString(1,id); statement.setString(2,etiqueta);
                    statement.setDouble(3,probabilidad); statement.setDouble(4,duracionMs); statement.executeUpdate();
                }
                complete(connection,id);
                connection.commit();
            } catch (SQLException | RuntimeException failure) { connection.rollback(); throw failure; }
        }
    }

    private static void complete(Connection connection, String id) throws SQLException {
        try (PreparedStatement statement = connection.prepareStatement(
                "UPDATE solicitudes SET estado='COMPLETADA' WHERE id_solicitud=?")) {
            statement.setString(1,id);
            if (statement.executeUpdate()!=1) throw new SQLException("request_missing", "23503");
        }
        try (PreparedStatement statement = connection.prepareStatement(
                "INSERT INTO historial_consultas(id_solicitud,id_cliente,evento) SELECT id_solicitud,id_cliente,'PERSISTIDA' FROM solicitudes WHERE id_solicitud=?")) {
            statement.setString(1,id); statement.executeUpdate();
        }
    }

    /** Classification, state, history and recoverable confirmation share one commit. */
    public com.google.gson.JsonObject persistir(com.google.gson.JsonObject message) throws Exception {
        com.google.gson.JsonObject payload = message.getAsJsonObject("payload");
        String id=message.get("idSolicitud").getAsString(), client=message.get("idCliente").getAsString();
        models.DatabaseMessages.validate(message,"GUARDAR_RESULTADO",id);
        models.DatabaseMessages.persistence(message);
        com.google.gson.JsonObject immutable=payload.deepCopy();
        immutable.remove("duracionMs"); // a recomputation after restart may take a different duration
        String hash=java.util.HexFormat.of().formatHex(java.security.MessageDigest.getInstance("SHA-256").digest(
            (client+"|A|"+models.DatabaseMessages.canonical(immutable).toString()).getBytes(java.nio.charset.StandardCharsets.UTF_8)));
        try (Connection connection=open()) {
            connection.setAutoCommit(false);
            try {
                com.google.gson.JsonObject image=payload.getAsJsonObject("imagen");
                try (PreparedStatement statement=connection.prepareStatement(
                        "INSERT INTO solicitudes(id_solicitud,id_cliente,modelo,nombre_archivo,tipo_imagen,sha256_imagen,estado,metadatos_imagen) VALUES(?,?,'A',?,?,?,'PROCESANDO',?::jsonb) ON CONFLICT DO NOTHING")) {
                    statement.setString(1,id);statement.setString(2,client);
                    statement.setString(3,image.get("nombre").getAsString());
                    statement.setString(4,image.get("mimeType").getAsString());
                    statement.setString(5,image.get("sha256").getAsString()); statement.setString(6,image.toString());statement.executeUpdate();
                }
                try (PreparedStatement statement=connection.prepareStatement(
                        "SELECT id_cliente,modelo,sha256_imagen FROM solicitudes WHERE id_solicitud=? FOR UPDATE")) {
                    statement.setString(1,id);
                    try (ResultSet row=statement.executeQuery()) {
                        if(!row.next() || !client.equals(row.getString(1)) || !"A".equals(row.getString(2))
                            || (row.getString(3)!=null && !image.get("sha256").getAsString().equals(row.getString(3))))
                            throw new SQLException("idempotency_conflict","23505");
                    }
                }
                try (PreparedStatement statement=connection.prepareStatement(
                        "UPDATE solicitudes SET nombre_archivo=COALESCE(nombre_archivo,?),tipo_imagen=COALESCE(tipo_imagen,?),sha256_imagen=COALESCE(sha256_imagen,?),metadatos_imagen=COALESCE(metadatos_imagen,?::jsonb) WHERE id_solicitud=?")) {
                    statement.setString(1,image.get("nombre").getAsString());statement.setString(2,image.get("mimeType").getAsString());
                    statement.setString(3,image.get("sha256").getAsString());statement.setString(4,image.toString());statement.setString(5,id);statement.executeUpdate();
                }
                try (PreparedStatement statement=connection.prepareStatement(
                        "SELECT huella,mensaje::text FROM outbox_persistencia WHERE id_solicitud=?")) {
                    statement.setString(1,id);
                    try (ResultSet row=statement.executeQuery()) {
                        if(row.next()) {
                            if(!hash.equals(row.getString(1))) throw new SQLException("idempotency_conflict","23505");
                            com.google.gson.JsonObject previous=com.google.gson.JsonParser.parseString(row.getString(2)).getAsJsonObject();
                            connection.commit(); return previous;
                        }
                    }
                }
                try(PreparedStatement statement=connection.prepareStatement(
                        "INSERT INTO clasificaciones(id_solicitud,etiqueta,probabilidad,duracion_ms,probabilidades) VALUES(?,?,?,?,?::jsonb)")) {
                    statement.setString(1,id);statement.setString(2,payload.get("etiqueta").getAsString());
                    statement.setDouble(3,payload.get("probabilidad").getAsDouble());
                    statement.setDouble(4,payload.get("duracionMs").getAsDouble());
                    statement.setString(5,payload.get("probabilidades").toString()); statement.executeUpdate();
                }
                complete(connection,id);
                com.google.gson.JsonObject result=message.deepCopy();
                result.addProperty("tipo","RESULTADO_PERSISTENCIA"); result.addProperty("estado","PERSISTIDA");
                result.addProperty("timestamp",java.time.Instant.now().toString()); result.add("payload",new com.google.gson.JsonObject());
                try(PreparedStatement statement=connection.prepareStatement(
                        "INSERT INTO outbox_persistencia(id_solicitud,huella,mensaje) VALUES(?,?,?::jsonb)")) {
                    statement.setString(1,id); statement.setString(2,hash); statement.setString(3,result.toString());statement.executeUpdate();
                }
                connection.commit(); return result;
            } catch(Exception failure) { connection.rollback(); throw failure; }
        }
    }

    /** Authenticated probe. Never calls the persistence methods above. */
    public static void main(String[] args) throws Exception {
        String user = System.getenv("POSTGRES_USER"), password = System.getenv("POSTGRES_PASSWORD");
        if (user == null || user.isEmpty() || password == null || password.isEmpty())
            throw new IllegalArgumentException("postgres_credentials_required");
        String url = "jdbc:postgresql://" + System.getenv().getOrDefault("POSTGRES_HOST", "127.0.0.1")
            + ":" + System.getenv().getOrDefault("POSTGRES_PORT", "5432") + "/"
            + System.getenv().getOrDefault("POSTGRES_DB", "pc3_concurrente");
        java.util.Properties properties = new java.util.Properties();
        properties.setProperty("user", user);
        properties.setProperty("password", password);
        properties.setProperty("connectTimeout", "5");
        properties.setProperty("socketTimeout", "5");
        try (Connection connection = DriverManager.getConnection(url, properties)) {
            connection.setReadOnly(true);
            connection.setAutoCommit(false);
            try (Statement statement = connection.createStatement()) {
                statement.setQueryTimeout(5);
                try (ResultSet result = statement.executeQuery("SELECT 1")) {
                    if (!result.next() || result.getInt(1) != 1) throw new SQLException("invalid_probe_response");
                }
            } finally { connection.rollback(); }
            System.out.println("OK: PostgreSQL autenticado; SELECT 1 READ ONLY y rollback; sin alterar datos");
        } catch (SQLException error) {
            System.err.println("FALLO: PostgreSQL SQLState=" + error.getSQLState());
            System.exit(1);
        }
    }
}
