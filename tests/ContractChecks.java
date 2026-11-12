import com.google.gson.Gson;
import models.MensajesRabbit;
import java.util.*;

public class ContractChecks {
    public static void main(String[] args) {
        Gson gson = new Gson();
        if (args.length == 0) {
            MensajesRabbit.PeticionIA request = new MensajesRabbit.PeticionIA();
            request.idSolicitud = "cross-language-1";
            request.idCliente = "contract-client";
            request.modeloDestino = "A";
            request.timestamp = java.time.Instant.now().toString();
            request.payload = new MensajesRabbit.PeticionIA.PayloadPeticion();
            request.payload.modo = "SEQUENTIAL";
            request.payload.imagen = new MensajesRabbit.PeticionIA.Imagen();
            request.payload.imagen.valores = Collections.nCopies(256, 0.25);
            System.out.println(gson.toJson(request));
        } else {
            MensajesRabbit.RespuestaIA response = gson.fromJson(args[0], MensajesRabbit.RespuestaIA.class);
            if (response.schemaVersion != 1 || !"cross-language-1".equals(response.idSolicitud)
                || !"COMPLETADA".equals(response.estado) || response.payload.probabilidades.size() != 3)
                throw new AssertionError("invalid_python_response");
            double sum = response.payload.probabilidades.stream().mapToDouble(Double::doubleValue).sum();
            if (Math.abs(sum - 1) > 1e-8) throw new AssertionError("invalid_probabilities");
            System.out.println("OK: Python -> Java");
        }
    }
}
