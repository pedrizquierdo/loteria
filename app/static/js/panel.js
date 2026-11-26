(function () {
  "use strict";

  var raiz = document.querySelector("[data-panel-state-url]");
  if (!raiz) {
    return;
  }

  var urlEstado = raiz.getAttribute("data-panel-state-url");
  var elStatus = raiz.querySelector("[data-panel-status]");
  var elPlayersCount = raiz.querySelector("[data-panel-players-count]");
  var elPlayersInline = raiz.querySelector("[data-panel-players-inline]");
  var elCalledCount = raiz.querySelector("[data-panel-called-count]");
  var elRemaining = raiz.querySelector("[data-panel-remaining]");
  var elError = raiz.querySelector("[data-panel-error]");
  var elWinnerBanner = raiz.querySelector("[data-panel-winner-banner]");
  var elWinnerName = raiz.querySelector("[data-panel-winner-name]");
  var elWinnerFigure = raiz.querySelector("[data-panel-winner-figure]");
  var elModeTag = raiz.querySelector("[data-panel-mode-tag]");
  var elCardOrder = raiz.querySelector("[data-panel-card-order]");
  var elCardId = raiz.querySelector("[data-panel-card-id]");
  var elCardName = raiz.querySelector("[data-panel-card-name]");
  var formStart = raiz.querySelector('[data-panel-action="start"]');
  var formNext = raiz.querySelector('[data-panel-action="next-card"]');
  var btnNext = raiz.querySelector("[data-panel-next-btn]");
  var autoNotice = raiz.querySelector("[data-panel-auto-notice]");
  var formSettings = raiz.querySelector("[data-panel-settings-form]");
  var btnSettings = raiz.querySelector("[data-panel-settings-btn]");
  var elPlayersList = raiz.querySelector("[data-panel-players-list]");
  var elPlayersEmpty = raiz.querySelector("[data-panel-players-empty]");
  var elHistoryList = raiz.querySelector("[data-panel-history-list]");
  var elHistoryEmpty = raiz.querySelector("[data-panel-history-empty]");

  function mostrarError(msg) {
    if (!elError) {
      return;
    }
    if (!msg) {
      elError.textContent = "";
      elError.classList.add("is-hidden");
      return;
    }
    elError.textContent = msg;
    elError.classList.remove("is-hidden");
  }

  function renderEstado(datos) {
    if (elStatus) {
      elStatus.textContent = datos.status_label;
      elStatus.className = "status-pill status-" + datos.status;
    }
    if (elPlayersCount) {
      elPlayersCount.textContent = String(datos.players_count);
    }
    if (elPlayersInline) {
      elPlayersInline.textContent = String(datos.players_count);
    }
    if (elCalledCount) {
      elCalledCount.textContent = String(datos.called_count) + " / 54";
    }
    if (elRemaining) {
      elRemaining.textContent = String(datos.remaining);
    }
    if (elModeTag) {
      elModeTag.textContent = datos.mode_label + " · " + datos.difficulty_label;
    }

    if (datos.current_card) {
      elCardOrder.textContent = "Carta #" + String(datos.current_card.order);
      elCardId.textContent = String(datos.current_card.id);
      elCardName.textContent = datos.current_card.name;
    } else {
      elCardOrder.textContent = "Listo para cantar";
      elCardId.textContent = "—";
      elCardName.textContent = "Aún no se canta ninguna carta";
    }

    if (formStart) {
      formStart.classList.toggle("is-hidden", datos.status !== "espera");
    }
    if (formNext) {
      formNext.classList.toggle(
        "is-hidden",
        datos.status !== "en_juego" || datos.mode !== "manual"
      );
    }
    if (btnNext) {
      btnNext.disabled = datos.remaining === 0;
    }
    if (autoNotice) {
      autoNotice.classList.toggle(
        "is-hidden",
        datos.status !== "en_juego" || datos.mode !== "auto"
      );
      autoNotice.textContent =
        "Modo automático activo: las cartas salen cada " +
        String(datos.interval_seconds) +
        " segundos.";
    }

    var terminada = datos.status === "terminada";
    if (formSettings) {
      formSettings.querySelectorAll("select").forEach(function (sel) {
        sel.disabled = terminada;
      });
    }
    if (btnSettings) {
      btnSettings.disabled = terminada;
    }

    if (elWinnerBanner) {
      if (datos.winner) {
        elWinnerName.textContent = datos.winner.username;
        elWinnerFigure.textContent = "Figura: " + datos.winner.figure_label;
        elWinnerBanner.classList.remove("is-hidden");
      } else {
        elWinnerBanner.classList.add("is-hidden");
      }
    }

    if (elPlayersList && Array.isArray(datos.players)) {
      elPlayersList.textContent = "";
      datos.players.forEach(function (nombre) {
        var li = document.createElement("li");
        li.className = "chip";
        li.textContent = nombre;
        elPlayersList.appendChild(li);
      });
      var hayJugadores = datos.players.length > 0;
      elPlayersList.classList.toggle("is-hidden", !hayJugadores);
      if (elPlayersEmpty) {
        elPlayersEmpty.classList.toggle("is-hidden", hayJugadores);
      }
    }

    if (elHistoryList && Array.isArray(datos.called_cards)) {
      elHistoryList.textContent = "";
      datos.called_cards
        .slice()
        .reverse()
        .forEach(function (carta) {
          var li = document.createElement("li");
          li.className = "history-item";

          var spanOrder = document.createElement("span");
          spanOrder.className = "history-order";
          spanOrder.textContent = "#" + String(carta.order);

          var strongName = document.createElement("strong");
          strongName.textContent = carta.name;

          var spanId = document.createElement("span");
          spanId.className = "history-id";
          spanId.textContent = "(" + String(carta.id) + ")";

          li.appendChild(spanOrder);
          li.appendChild(strongName);
          li.appendChild(spanId);
          elHistoryList.appendChild(li);
        });
      var hayCantadas = datos.called_cards.length > 0;
      elHistoryList.classList.toggle("is-hidden", !hayCantadas);
      if (elHistoryEmpty) {
        elHistoryEmpty.classList.toggle("is-hidden", hayCantadas);
      }
    }
  }

  function enviarAccion(url, cuerpo) {
    mostrarError("");
    var opciones = {
      method: "POST",
      headers: { Accept: "application/json" },
    };
    if (cuerpo) {
      opciones.headers["Content-Type"] = "application/json";
      opciones.body = JSON.stringify(cuerpo);
    }
    return fetch(url, opciones)
      .then(function (resp) {
        return resp.json().then(function (datos) {
          if (!resp.ok) {
            mostrarError(datos.error || "No se pudo completar la acción.");
            return;
          }
          renderEstado(datos);
        });
      })
      .catch(function () {
        mostrarError("Error de conexión con el servidor.");
      });
  }

  [formStart, formNext].forEach(function (form) {
    if (!form) {
      return;
    }
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      enviarAccion(form.getAttribute("action"));
    });
  });

  if (formSettings) {
    formSettings.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var cuerpo = {
        figure: formSettings.elements.figure.value,
        mode: formSettings.elements.mode.value,
        difficulty: formSettings.elements.difficulty.value,
      };
      enviarAccion(formSettings.getAttribute("action"), cuerpo);
    });
  }

  window.setInterval(function () {
    if (document.hidden) {
      return;
    }
    fetch(urlEstado, { headers: { Accept: "application/json" } })
      .then(function (resp) {
        return resp.ok ? resp.json() : null;
      })
      .then(function (datos) {
        if (datos && !datos.error) {
          renderEstado(datos);
        }
      })
      .catch(function () {});
  }, 1500);
})();
