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

    // Guarda la solicitud inicial cuando llega del cliente
    public void guardarSolicitud(String id, String cliente, String modelo, String estado) {
        String sql = "INSERT INTO solicitudes (id_solicitud, id_cliente, modelo, estado) VALUES (?, ?, ?, ?) " +
                     "ON CONFLICT (id_solicitud) DO UPDATE SET estado = EXCLUDED.estado";
        try (Connection conn = DriverManager.getConnection(url, user, password);
             PreparedStatement pstmt = conn.prepareStatement(sql)) {
            pstmt.setString(1, id);
            pstmt.setString(2, cliente);
            pstmt.setString(3, modelo);
            pstmt.setString(4, estado);
            pstmt.executeUpdate();
            System.out.println(" [DB] Solicitud guardada/actualizada: " + id);
        } catch (SQLException e) {
            System.err.println("Error BD (guardarSolicitud): " + e.getMessage());
        }
    }

    // Guarda el resultado de la IA y actualiza el estado a COMPLETADA
    public void guardarResultado(String id, String etiqueta, double probabilidad, double duracionMs) {
        String sql = "INSERT INTO clasificaciones (id_solicitud, etiqueta, probabilidad, duracion_ms) VALUES (?, ?, ?, ?)";
        try (Connection conn = DriverManager.getConnection(url, user, password);
             PreparedStatement pstmt = conn.prepareStatement(sql)) {
            pstmt.setString(1, id);
            pstmt.setString(2, etiqueta);
            pstmt.setBigDecimal(3, java.math.BigDecimal.valueOf(probabilidad));
            pstmt.setBigDecimal(4, java.math.BigDecimal.valueOf(duracionMs));
            pstmt.executeUpdate();
            
            // Actualizamos el estado en la tabla principal
            guardarSolicitud(id, "", "", "COMPLETADA"); 
            System.out.println(" [DB] Resultado guardado para: " + id);
        } catch (SQLException e) {
            System.err.println("Error BD (guardarResultado): " + e.getMessage());
        }
    }

    // =========================================================
    // MÉTODO DE PRUEBA (BORRAR DESPUÉS)
    // =========================================================
    public static void main(String[] args) {
        // ATENCIÓN: Cambia el puerto (5432), usuario (postgres) y contraseña ("tu_contraseña")
        // según cómo lo tengas configurado en tu PostgreSQL.
        PostgresManager db = new PostgresManager("localhost", 5432, "pc3_concurrente", "postgres", "postgresql17");
        
        System.out.println("Probando conexión a PostgreSQL...");
        db.guardarSolicitud("test-123", "cliente-prueba", "A", "RECIBIDA");
        db.guardarResultado("test-123", "circulo", 0.95, 1200.5);
    }
}