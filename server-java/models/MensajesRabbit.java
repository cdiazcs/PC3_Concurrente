package models;

import java.util.List;

public class MensajesRabbit {
    
    public static class PeticionIA {
        public int schemaVersion = 1;
        public String idSolicitud;
        public String idCliente;
        public String timestamp;
        public String tipo = "INFERENCIA";
        public String modeloDestino;
        public int intento = 1;
        public PayloadPeticion payload;

        public static class PayloadPeticion {
            public String modo;
            public Imagen imagen;
        }
        public static class Imagen {
            public String formato = "VECTOR_NORMALIZADO";
            public int ancho = 16;
            public int alto = 16;
            public List<Double> valores;
        }
    }

    public static class RespuestaIA {
        public String idCliente;
        public String modeloDestino;
        public String tipo;
        public int schemaVersion = 1;
        public String idSolicitud;
        public String timestamp;
        public String estado; 
        public PayloadRespuesta payload;
        public String error;

        public static class PayloadRespuesta {
            public String etiqueta;
            public double probabilidad;
            public List<Double> probabilidades;
            public double duracionMs;
        }
    }
}