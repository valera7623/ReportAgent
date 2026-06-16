import { adminApi, onError } from "../api.js";
import { mountShell } from "../layout.js";
import { confirmDialog, loadingHtml, showModal, toast } from "../ui.js";
import { escapeHtml, formatDate, formatRubles, paymentStatusClass, truncateId } from "../utils.js";

const STATUS_OPTIONS = [
  { value: "", label: "Все статусы" },
  { value: "pending", label: "pending" },
  { value: "waiting_for_capture", label: "waiting_for_capture" },
  { value: "succeeded", label: "succeeded" },
  { value: "canceled", label: "canceled" },
];

function getStatusFilter() {
  const q = location.hash.split("?")[1] || "";
  return new URLSearchParams(q).get("status") || "";
}

function setStatusFilter(status) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  location.hash = `#/admin/payments${params.toString() ? `?${params}` : ""}`;
}

export async function renderAdminPayments(root) {
  mountShell(root, "Платежи ЮKassa", loadingHtml());
  const statusFilter = getStatusFilter();

  try {
    const data = await adminApi.payments({ status_filter: statusFilter || undefined });
    const rows =
      data.payments.length === 0
        ? `<tr><td colspan="8" class="empty-state">Платежей нет</td></tr>`
        : data.payments
            .map(
              (p) => `
        <tr>
          <td class="mono" title="${escapeHtml(p.payment_id)}">${truncateId(p.payment_id, 10)}</td>
          <td class="mono" title="${escapeHtml(p.user_id)}">${truncateId(p.user_id, 8)}</td>
          <td>${formatRubles(p.amount)}</td>
          <td><span class="badge ${paymentStatusClass(p.status)}">${escapeHtml(p.status)}</span></td>
          <td>${escapeHtml(p.payment_method || "—")}</td>
          <td>${formatDate(p.created_at)}</td>
          <td>${formatDate(p.captured_at)}</td>
          <td class="td-actions">
            <button class="btn-icon" data-view="${escapeHtml(p.payment_id)}" title="Детали">👁</button>
            ${
              p.status === "succeeded"
                ? `<button class="btn-icon" data-refund="${escapeHtml(p.payment_id)}" title="Возврат">↩</button>`
                : ""
            }
          </td>
        </tr>`,
            )
            .join("");

    const filterOptions = STATUS_OPTIONS.map(
      (o) => `<option value="${o.value}" ${statusFilter === o.value ? "selected" : ""}>${o.label}</option>`,
    ).join("");

    mountShell(
      root,
      "Платежи ЮKassa",
      `
      <div class="page-header" style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:1rem">
        <div>
          <h2>Платежи ЮKassa</h2>
          <p>Всего: ${data.total}</p>
        </div>
        <select id="payment-status-filter">${filterOptions}</select>
      </div>
      <div class="table-wrap"><table>
        <thead>
          <tr>
            <th>Payment ID</th>
            <th>User</th>
            <th>Сумма</th>
            <th>Статус</th>
            <th>Метод</th>
            <th>Создан</th>
            <th>Захвачен</th>
            <th></th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table></div>`,
      (el) => bindAdminPayments(el, root),
    );
  } catch (err) {
    onError(err);
  }
}

function bindAdminPayments(root, appRoot) {
  root.querySelector("#payment-status-filter")?.addEventListener("change", (e) => {
    setStatusFilter(e.target.value);
  });

  root.querySelectorAll("[data-view]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        const detail = await adminApi.payment(btn.dataset.view);
        const meta = detail.metadata ? JSON.stringify(detail.metadata, null, 2) : "{}";
        await showModal({
          title: `Платёж ${truncateId(btn.dataset.view, 12)}`,
          body: `
            <p><b>Статус:</b> ${escapeHtml(detail.status)}</p>
            <p><b>Сумма:</b> ${formatRubles(detail.amount)}</p>
            <p><b>User:</b> <span class="mono">${escapeHtml(detail.user_id)}</span></p>
            <p><b>Описание:</b> ${escapeHtml(detail.description || "—")}</p>
            <p><b>Метод:</b> ${escapeHtml(detail.payment_method || "—")}</p>
            <p><b>Создан:</b> ${formatDate(detail.created_at)}</p>
            <p><b>Захвачен:</b> ${formatDate(detail.captured_at)}</p>
            <pre class="mono" style="margin-top:1rem;white-space:pre-wrap;font-size:.8rem">${escapeHtml(meta)}</pre>`,
          footer: `<button class="btn" data-modal-action="true">Закрыть</button>`,
        });
      } catch (err) {
        onError(err);
      }
    };
  });

  root.querySelectorAll("[data-refund]").forEach((btn) => {
    btn.onclick = async () => {
      const id = btn.dataset.refund;
      if (!(await confirmDialog("Возврат платежа?", `Будет выполнен полный возврат для ${truncateId(id, 12)}.`))) {
        return;
      }
      try {
        const res = await adminApi.refundPayment(id);
        toast(`Возврат создан: ${res.refund?.id || "ok"}`, "success");
        renderAdminPayments(appRoot);
      } catch (err) {
        onError(err);
      }
    };
  });
}
