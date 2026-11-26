(function () {
  "use strict";

  // 1. Normaliza a mayúsculas y quita espacios mientras el alumno teclea el código.
  document.querySelectorAll("[data-uppercase-code]").forEach(function (input) {
    input.addEventListener("input", function () {
      var limpio = input.value.replace(/\s+/g, "").toUpperCase();
      if (input.value !== limpio) {
        input.value = limpio;
      }
    });
  });

  // 2. Botones de copiar código y enlace (funciona en HTTPS y en red local HTTP).
  function copiarTexto(texto) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(texto);
    }
    return new Promise(function (resolve, reject) {
      var area = document.createElement("textarea");
      area.value = texto;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.opacity = "0";
      document.body.appendChild(area);
      area.select();
      try {
        var ok = document.execCommand("copy");
        document.body.removeChild(area);
        if (ok) {
          resolve();
        } else {
          reject(new Error("No se pudo copiar"));
        }
      } catch (err) {
        document.body.removeChild(area);
        reject(err);
      }
    });
  }

  document.querySelectorAll("[data-copy-text]").forEach(function (boton) {
    boton.addEventListener("click", function () {
      var texto = boton.getAttribute("data-copy-text") || "";
      var etiquetaOriginal = boton.textContent;
      copiarTexto(texto)
        .then(function () {
          boton.textContent = "¡Copiado!";
          window.setTimeout(function () {
            boton.textContent = etiquetaOriginal;
          }, 1800);
        })
        .catch(function () {
          boton.textContent = "Selecciona y copia";
          window.setTimeout(function () {
            boton.textContent = etiquetaOriginal;
          }, 2200);
        });
    });
  });

  // 3. Actualización automática en vivo de la sala (profesor y alumno).
  var contenedorSala = document.querySelector("[data-room-poll]");
  if (!contenedorSala) {
    return;
  }

  var urlEstado = contenedorSala.getAttribute("data-room-poll");
  var rol = contenedorSala.getAttribute("data-room-role");
  var elConteo = contenedorSala.querySelector("[data-players-count]");
  var elLista = contenedorSala.querySelector("[data-players-list]");
  var elVacio = contenedorSala.querySelector("[data-players-empty]");
  var elEstado = contenedorSala.querySelector("[data-room-status]");
  var elFigura = contenedorSala.querySelector("[data-room-figure]");
  var elFiguraDesc = contenedorSala.querySelector("[data-room-figure-desc]");
  var elModo = contenedorSala.querySelector("[data-room-mode]");
  var elDificultad = contenedorSala.querySelector("[data-room-difficulty]");
  var elBannerAlumno = contenedorSala.querySelector("[data-player-status-banner]");

  var MENSAJES_ALUMNO = {
    espera: "Ya estás dentro de la sala. Esperando a que el profesor inicie la partida…",
    en_juego: "¡La partida está en juego! Presta atención a las cartas que cante tu profesor.",
    terminada: "Esta partida ya terminó. Aquí puedes consultar tu tablero asignado.",
  };

  function aplicarEstado(datos) {
    if (elConteo && typeof datos.players_count === "number") {
      elConteo.textContent = String(datos.players_count);
    }

    if (elEstado && datos.status && datos.status_label) {
      elEstado.textContent = datos.status_label;
      elEstado.className = "status-pill status-" + datos.status;
    }

    if (elFigura && datos.figure_label) {
      elFigura.textContent = datos.figure_label;
    }

    if (elFiguraDesc && datos.figure_description) {
      elFiguraDesc.textContent = datos.figure_description;
    }

    if (elModo && datos.mode_label) {
      elModo.textContent = datos.mode_label;
    }

    if (elDificultad && datos.difficulty_label) {
      elDificultad.textContent = datos.difficulty_label;
    }

    if (rol === "profesor" && elLista && Array.isArray(datos.players)) {
      elLista.textContent = "";
      datos.players.forEach(function (nombre) {
        var li = document.createElement("li");
        li.className = "player-chip";
        li.textContent = nombre;
        elLista.appendChild(li);
      });
      var hayJugadores = datos.players.length > 0;
      elLista.classList.toggle("is-hidden", !hayJugadores);
      if (elVacio) {
        elVacio.classList.toggle("is-hidden", hayJugadores);
      }
    }

    if (rol === "jugador" && elBannerAlumno && datos.status) {
      elBannerAlumno.textContent =
        MENSAJES_ALUMNO[datos.status] || datos.status_label || "";
      elBannerAlumno.className = "status-banner status-banner-" + datos.status;
    }
  }

  function consultarEstado() {
    if (document.hidden) {
      return;
    }
    fetch(urlEstado, { headers: { Accept: "application/json" } })
      .then(function (resp) {
        if (!resp.ok) {
          return null;
        }
        return resp.json();
      })
      .then(function (datos) {
        if (datos && !datos.error) {
          aplicarEstado(datos);
        }
      })
      .catch(function () {
        // Error temporal de red: se reintentará en el siguiente ciclo.
      });
  }

  window.setInterval(consultarEstado, 2000);
})();
