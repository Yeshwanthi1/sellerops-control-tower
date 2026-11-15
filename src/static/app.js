// SellerOps Control Tower Dashboard Logic
let currentRole = "OPS_MANAGER";
let activePayoutId = null;

// Pagination states
let sellerPage = 1;
let fulPage = 1;
let payoutPage = 1;
let eventPage = 1;

// Initial bootstrap
document.addEventListener("DOMContentLoaded", () => {
  loadOverviewKPIs();
  loadExceptions();
  loadCustomerReviews();
  loadFulfillments(1);
  loadSellers(1);
  loadPayouts(1);
  loadEvaluation();
  loadEvents(1);
});

// Role Management
function switchRole(role) {
  currentRole = role;
  const bannerTitle = document.getElementById("roleBannerTitle");
  const bannerDesc = document.getElementById("roleBannerDesc");

  if (role === "OPS_MANAGER") {
    bannerTitle.textContent = "Operations Manager Console";
    bannerDesc.textContent = "Full visibility over financial controls, payout reconciliations, risk reserves, and exception queues.";
    switchTab("overview");
  } else if (role === "WAREHOUSE_OPERATOR") {
    bannerTitle.textContent = "Warehouse Fulfillment Workspace";
    bannerDesc.textContent = "Manage pick, pack, and shipment queues. Monitor carrier dispatch and carrier delivery SLA deadlines.";
    switchTab("warehouse");
  } else if (role === "ANALYST") {
    bannerTitle.textContent = "Performance Analyst Console";
    bannerDesc.textContent = "Evaluate seller SLA compliance, on-time delivery rates, dispute trends, and category commission yield.";
    switchTab("analyst");
  } else if (role === "CUSTOMER") {
    bannerTitle.textContent = "Customer Portal";
    bannerDesc.textContent = "Track multi-seller order progress, inspect carrier tracking, and browse verified customer reviews.";
    switchTab("customer");
  }
}

// Tab Navigation
function switchTab(tabId) {
  document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));

  const targetPane = document.getElementById(`tab-${tabId}`);
  if (targetPane) targetPane.classList.add("active");

  const btnIndex = {
    "overview": 0, "customer": 1, "warehouse": 2, "analyst": 3,
    "financials": 4, "exceptions": 5, "evaluation": 6, "events": 7, "exports": 8
  }[tabId];

  const btns = document.querySelectorAll(".tab-btn");
  if (btns[btnIndex]) btns[btnIndex].classList.add("active");
}

function renderPaginationControls(containerId, page, totalPages, totalItems, onPageChange) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (totalPages <= 1) {
    container.innerHTML = `<div style="font-size:0.8rem; color:var(--text-muted); padding:0.5rem 0;">Showing ${totalItems} total records</div>`;
    return;
  }
  container.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; padding:0.75rem 0; font-size:0.85rem;">
      <div style="color:var(--text-muted);">
        Page <strong>${page}</strong> of <strong>${totalPages}</strong> (${totalItems.toLocaleString()} total items)
      </div>
      <div style="display:flex; gap:0.5rem; align-items:center;">
        <button class="btn btn-sm" ${page <= 1 ? 'disabled style="opacity:0.5;cursor:not-allowed;"' : ''} onclick="${onPageChange}(${page - 1})">← Previous</button>
        <span style="font-size:0.8rem; color:var(--text-muted);">Page ${page} / ${totalPages}</span>
        <button class="btn btn-sm" ${page >= totalPages ? 'disabled style="opacity:0.5;cursor:not-allowed;"' : ''} onclick="${onPageChange}(${page + 1})">Next →</button>
      </div>
    </div>
  `;
}

// 1. Overview KPIs
async function loadOverviewKPIs() {
  try {
    const res = await fetch("/api/summary");
    const d = await res.json();

    document.getElementById("kpiGMV").textContent = `$${d.orders.gmv.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
    document.getElementById("kpiOrders").textContent = `${d.orders.total.toLocaleString()} Total Orders`;

    document.getElementById("kpiOnTimeShip").textContent = `${d.sla.on_time_ship_pct}%`;
    document.getElementById("kpiLateShip").textContent = `${d.sla.late_shipment_count} Late Shipments`;

    document.getElementById("kpiOnTimeDeliv").textContent = `${d.sla.on_time_delivery_pct}%`;
    document.getElementById("kpiLateDeliv").textContent = `${d.sla.late_delivery_count} Late Deliveries`;

    document.getElementById("kpiCommissions").textContent = `$${d.financials.commission_collected.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
    document.getElementById("kpiReserves").textContent = `$${d.financials.reserves_held.toLocaleString(undefined, {minimumFractionDigits: 2})}`;

    document.getElementById("kpiDisputes").textContent = d.disputes.total.toLocaleString();
    document.getElementById("kpiDisputeAmt").textContent = `$${d.disputes.total_amount.toLocaleString(undefined, {minimumFractionDigits: 2})} Total (${d.disputes.dispute_rate_pct}% of orders)`;

    document.getElementById("kpiExceptions").textContent = d.exceptions.total;
    document.getElementById("kpiCriticalExceptions").textContent = `${d.exceptions.critical} Critical Severity`;
    document.getElementById("badgeExceptions").textContent = d.exceptions.total;

    document.getElementById("cntActiveSellers").textContent = d.sellers.active;
    document.getElementById("cntSuspendedSellers").textContent = d.sellers.suspended;
    document.getElementById("cntTotalSellers").textContent = d.sellers.total;

    document.getElementById("cntPayouts").textContent = d.financials.payouts_count;
    document.getElementById("cntNetPaid").textContent = `$${d.financials.net_paid.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
  } catch (err) {
    console.error("Failed to load overview KPIs", err);
  }
}

// 2. Customer Order Tracking
async function searchCustomerOrder() {
  const input = document.getElementById("custOrderSearchInput");
  const orderId = input.value.trim();
  if (!orderId) return alert("Please enter an Order ID (e.g. ORD-2026-000001)");

  try {
    const res = await fetch(`/api/orders/${orderId}`);
    if (!res.ok) throw new Error("Order not found");
    const order = await res.json();

    document.getElementById("custOrderDetails").style.display = "block";
    document.getElementById("custDetailOrderId").textContent = order.order_id;
    document.getElementById("custDetailOrderDate").textContent = `Placed: ${order.order_date} | Total: $${order.total_amount.toFixed(2)}`;
    document.getElementById("custDetailAddress").textContent = order.shipping_address;

    const badge = document.getElementById("custDetailStatusBadge");
    badge.textContent = order.status;
    badge.className = `badge ${order.status === 'DELIVERED' ? 'badge-green' : 'badge-blue'}`;

    const linesBody = document.getElementById("custOrderLinesTable");
    linesBody.innerHTML = order.order_lines.map(line => `
      <tr>
        <td><code>${line.order_line_id}</code></td>
        <td><strong>${line.listing_title}</strong><br><span style="font-size:0.75rem; color:var(--text-muted);">${line.category}</span></td>
        <td>${line.seller_name} <span class="badge badge-blue">${line.seller_tier}</span></td>
        <td>${line.quantity}</td>
        <td>$${line.unit_price.toFixed(2)}</td>
        <td><strong>$${line.subtotal.toFixed(2)}</strong></td>
        <td><span class="badge ${line.fulfillment_status === 'DELIVERED' ? 'badge-green' : (line.fulfillment_status === 'RETURNED' ? 'badge-red' : 'badge-amber')}">${line.fulfillment_status || 'PENDING'}</span></td>
        <td>${line.carrier || 'Pending'} <br><code>${line.tracking_number || '-'}</code></td>
      </tr>
    `).join("");
  } catch (err) {
    alert(`Could not locate order: ${orderId}`);
  }
}

async function loadCustomerReviews() {
  try {
    const res = await fetch("/api/reviews");
    const reviews = await res.json();
    const body = document.getElementById("customerReviewsTable");
    body.innerHTML = reviews.slice(0, 15).map(r => `
      <tr>
        <td><code>${r.review_id}</code></td>
        <td><code>${r.order_id}</code></td>
        <td>${r.seller_name}</td>
        <td>${r.product_title}</td>
        <td><span style="color:var(--accent-amber); font-weight:700;">${'★'.repeat(r.rating)}${'☆'.repeat(5-r.rating)}</span> (${r.rating}/5)</td>
        <td><strong>${r.title}</strong><br><span style="font-size:0.8rem; color:var(--text-muted);">${r.comment}</span></td>
        <td>${r.created_at}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Failed to load reviews", err);
  }
}

// 3. Warehouse Fulfillments
async function loadFulfillments(page = 1) {
  fulPage = page;
  const status = document.getElementById("warehouseStatusFilter").value;
  const carrier = document.getElementById("warehouseCarrierFilter").value;
  const lateOnly = document.getElementById("warehouseLateOnly").checked ? "1" : "0";

  try {
    const url = `/api/fulfillments?page=${page}&limit=50&status=${status}&carrier=${carrier}&late_only=${lateOnly}`;
    const res = await fetch(url);
    const data = await res.json();
    const list = data.items ? data.items : data;
    const total = data.total !== undefined ? data.total : list.length;
    const totalPages = data.total_pages !== undefined ? data.total_pages : 1;

    const tbody = document.getElementById("warehouseFulfillmentsTable");
    tbody.innerHTML = list.map(f => {
      const isLate = f.is_late_shipment || f.is_late_delivery;
      let actionButtons = "";

      if (f.status === "ALLOCATED") {
        actionButtons = `<button class="btn btn-sm btn-primary" onclick="updateFulfillmentStatus('${f.fulfillment_id}', 'PICKED')">Pick</button>`;
      } else if (f.status === "PICKED") {
        actionButtons = `<button class="btn btn-sm btn-primary" onclick="updateFulfillmentStatus('${f.fulfillment_id}', 'PACKED')">Pack</button>`;
      } else if (f.status === "PACKED") {
        actionButtons = `<button class="btn btn-sm btn-success" onclick="updateFulfillmentStatus('${f.fulfillment_id}', 'SHIPPED')">Ship Carrier</button>`;
      } else if (f.status === "SHIPPED") {
        actionButtons = `<button class="btn btn-sm btn-success" onclick="updateFulfillmentStatus('${f.fulfillment_id}', 'DELIVERED')">Confirm Delivery</button>`;
      } else {
        actionButtons = `<span style="font-size:0.75rem; color:var(--text-muted);">Completed</span>`;
      }

      return `
        <tr>
          <td><code>${f.fulfillment_id}</code></td>
          <td><code>${f.order_line_id}</code></td>
          <td>${f.seller_name}</td>
          <td>${f.product_title}</td>
          <td><span class="badge badge-purple">${f.carrier}</span></td>
          <td><code>${f.tracking_number}</code></td>
          <td>
            <span class="badge ${f.status === 'DELIVERED' ? 'badge-green' : (f.status === 'RETURNED' ? 'badge-red' : 'badge-blue')}">${f.status}</span>
            ${isLate ? '<span class="badge badge-red" style="margin-left:4px;">LATE SLA</span>' : ''}
          </td>
          <td>${f.sla_ship_deadline}</td>
          <td>${f.sla_delivery_deadline}</td>
          <td>${actionButtons}</td>
        </tr>
      `;
    }).join("");

    renderPaginationControls("warehousePagination", fulPage, totalPages, total, "loadFulfillments");
  } catch (err) {
    console.error("Failed to load fulfillments", err);
  }
}

async function updateFulfillmentStatus(fulId, newStatus) {
  try {
    const res = await fetch(`/api/fulfillments/${fulId}/update-status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus, actor: currentRole })
    });
    if (res.ok) {
      loadFulfillments(fulPage);
      loadOverviewKPIs();
      loadEvents(1);
    }
  } catch (err) {
    alert("Failed to update status");
  }
}

// 4. Analyst Sellers
async function loadSellers(page = 1) {
  sellerPage = page;
  const status = document.getElementById("sellerStatusFilter").value;
  const tier = document.getElementById("sellerTierFilter").value;
  const search = document.getElementById("sellerSearchInput").value.trim();

  try {
    const res = await fetch(`/api/sellers?page=${page}&limit=50&status=${status}&tier=${tier}&search=${encodeURIComponent(search)}`);
    const data = await res.json();
    const sellers = data.items ? data.items : data;
    const total = data.total !== undefined ? data.total : sellers.length;
    const totalPages = data.total_pages !== undefined ? data.total_pages : 1;

    const tbody = document.getElementById("sellersTable");
    tbody.innerHTML = sellers.map(s => `
      <tr>
        <td><code>${s.seller_id}</code></td>
        <td><strong>${s.name}</strong><br><span style="font-size:0.75rem; color:var(--text-muted);">${s.email}</span></td>
        <td><span class="badge badge-blue">${s.tier}</span></td>
        <td><span class="badge ${s.status === 'ACTIVE' ? 'badge-green' : (s.status === 'SUSPENDED' ? 'badge-red' : 'badge-amber')}">${s.status}</span></td>
        <td>${(s.reserve_rate * 100).toFixed(0)}%</td>
        <td>${s.hold_period_days} Days</td>
        <td><strong style="color:${s.on_time_ship_pct >= 90 ? 'var(--accent-green)' : 'var(--accent-red)'}">${s.on_time_ship_pct}%</strong></td>
        <td>${s.listing_count}</td>
        <td>${s.fulfillment_count}</td>
        <td>${s.dispute_count > 0 ? `<span class="badge badge-red">${s.dispute_count}</span>` : '0'}</td>
        <td>$${s.total_paid.toLocaleString(undefined, {minimumFractionDigits: 2})}</td>
        <td><button class="btn btn-sm btn-primary" onclick="viewSellerDetail('${s.seller_id}')">Scorecard</button></td>
      </tr>
    `).join("");

    renderPaginationControls("sellerPagination", sellerPage, totalPages, total, "loadSellers");
  } catch (err) {
    console.error("Failed to load sellers", err);
  }
}

function filterSellers() {
  loadSellers(1);
}

async function viewSellerDetail(sellerId) {
  try {
    const res = await fetch(`/api/sellers/${sellerId}`);
    const s = await res.json();

    document.getElementById("sellerModalTitle").textContent = `${s.name} (${s.seller_id})`;
    document.getElementById("sellerModalInfo").innerHTML = `
      <div style="display:grid; grid-template-columns: repeat(4, 1fr); gap:0.5rem; background:var(--bg-card); padding:1rem; border-radius:var(--radius-md);">
        <div><div style="font-size:0.75rem; color:var(--text-muted);">Status</div><strong>${s.status}</strong></div>
        <div><div style="font-size:0.75rem; color:var(--text-muted);">Tier</div><strong>${s.tier}</strong></div>
        <div><div style="font-size:0.75rem; color:var(--text-muted);">Reserve Rate</div><strong>${(s.reserve_rate*100).toFixed(0)}%</strong></div>
        <div><div style="font-size:0.75rem; color:var(--text-muted);">Hold Window</div><strong>${s.hold_period_days} Days</strong></div>
      </div>
    `;

    const listingsBody = document.getElementById("sellerModalListings");
    listingsBody.innerHTML = s.listings.map(l => `
      <tr>
        <td><code>${l.listing_id}</code></td>
        <td>${l.title}</td>
        <td>${l.category}</td>
        <td>$${l.price.toFixed(2)}</td>
        <td>${l.inventory_count}</td>
        <td><span class="badge ${l.status === 'ACTIVE' ? 'badge-green' : 'badge-amber'}">${l.status}</span></td>
      </tr>
    `).join("");

    openModal("sellerModal");
  } catch (err) {
    alert("Error fetching seller details");
  }
}

// 5. Payouts
async function loadPayouts(page = 1) {
  payoutPage = page;
  const status = document.getElementById("payoutStatusFilter").value;
  try {
    const res = await fetch(`/api/payouts?page=${page}&limit=50&status=${status}`);
    const data = await res.json();
    const payouts = data.items ? data.items : data;
    const total = data.total !== undefined ? data.total : payouts.length;
    const totalPages = data.total_pages !== undefined ? data.total_pages : 1;

    const tbody = document.getElementById("payoutsTable");
    tbody.innerHTML = payouts.map(p => `
      <tr>
        <td><code>${p.payout_id}</code></td>
        <td>${p.seller_name} <span class="badge badge-blue">${p.seller_tier}</span></td>
        <td>${p.period_start} to ${p.period_end}</td>
        <td>$${p.gross_amount.toFixed(2)}</td>
        <td style="color:var(--accent-red);">- $${p.commission_deduction.toFixed(2)}</td>
        <td style="color:var(--accent-amber);">- $${p.reserve_deduction.toFixed(2)}</td>
        <td style="color:var(--accent-red);">${p.dispute_deduction > 0 ? `- $${p.dispute_deduction.toFixed(2)}` : '$0.00'}</td>
        <td><strong style="color:var(--accent-green); font-size:1rem;">$${p.net_amount.toFixed(2)}</strong></td>
        <td><span class="badge ${p.status === 'PAID' ? 'badge-green' : (p.status === 'HELD' ? 'badge-red' : 'badge-amber')}">${p.status}</span></td>
        <td>${p.hold_release_date}</td>
        <td>${p.released_at || 'Pending'}</td>
        <td><button class="btn btn-sm btn-primary" onclick="viewPayoutDetail('${p.payout_id}')">Breakdown</button></td>
      </tr>
    `).join("");

    renderPaginationControls("payoutPagination", payoutPage, totalPages, total, "loadPayouts");
  } catch (err) {
    console.error("Failed to load payouts", err);
  }
}

async function viewPayoutDetail(payoutId) {
  activePayoutId = payoutId;
  try {
    const res = await fetch(`/api/payouts/${payoutId}`);
    const p = await res.json();

    document.getElementById("payoutModalTitle").textContent = `Payout Settlement ${p.payout_id} (${p.seller_name})`;
    document.getElementById("payoutModalSummary").innerHTML = `
      <div><div style="font-size:0.75rem; color:var(--text-muted);">Gross Sales</div><strong>$${p.gross_amount.toFixed(2)}</strong></div>
      <div><div style="font-size:0.75rem; color:var(--text-muted);">Commission Fee</div><strong style="color:var(--accent-red);">- $${p.commission_deduction.toFixed(2)}</strong></div>
      <div><div style="font-size:0.75rem; color:var(--text-muted);">Reserve Held</div><strong style="color:var(--accent-amber);">- $${p.reserve_deduction.toFixed(2)}</strong></div>
      <div><div style="font-size:0.75rem; color:var(--text-muted);">Net Disbursed</div><strong style="color:var(--accent-green); font-size:1.1rem;">$${p.net_amount.toFixed(2)}</strong></div>
    `;

    const linesBody = document.getElementById("payoutModalLines");
    linesBody.innerHTML = p.lines.map(line => `
      <tr>
        <td><code>${line.payout_line_id}</code></td>
        <td><code>${line.order_line_id}</code></td>
        <td><span class="badge ${line.line_type === 'GROSS_SALES' ? 'badge-green' : 'badge-amber'}">${line.line_type}</span></td>
        <td><strong style="color:${line.amount >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'}">$${line.amount.toFixed(2)}</strong></td>
        <td>${line.description}</td>
      </tr>
    `).join("");

    openModal("payoutModal");
  } catch (err) {
    alert("Error fetching payout detail");
  }
}

async function payoutAction(action) {
  if (!activePayoutId) return;
  try {
    const res = await fetch(`/api/payouts/${activePayoutId}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: action, actor: currentRole })
    });
    const result = await res.json();
    if (!res.ok) {
      alert(`[ACTION BLOCKED]\n${result.error}\n\nRule: ${result.rule || ''}\nViolations:\n- ${result.violations ? result.violations.join('\n- ') : 'Policy constraint violation'}`);
      return;
    }
    alert(`Payout ${activePayoutId} successfully updated to ${result.new_status}!`);
    closeModal("payoutModal");
    loadPayouts(payoutPage);
    loadOverviewKPIs();
    loadEvents(1);
  } catch (err) {
    alert("Action failed: " + err.message);
  }
}

// 6. Exception Queue
async function loadExceptions() {
  try {
    const res = await fetch("/api/exceptions");
    const data = await res.json();
    const tbody = document.getElementById("exceptionsTable");
    document.getElementById("badgeExceptions").textContent = data.count;

    tbody.innerHTML = data.exceptions.map(e => `
      <tr>
        <td><code>${e.exception_id}</code></td>
        <td><span class="badge ${e.severity === 'CRITICAL' ? 'badge-red' : 'badge-amber'}">${e.severity}</span></td>
        <td><strong>${e.issue_type}</strong></td>
        <td><code>${e.target_entity_type}: ${e.target_entity_id}</code></td>
        <td><code>${e.seller_id}</code></td>
        <td><strong style="color:var(--accent-red);">$${e.financial_impact.toFixed(2)}</strong></td>
        <td><span style="font-size:0.8rem;">${e.rule_violated}</span></td>
        <td><span style="font-size:0.8rem; color:var(--text-muted);">${e.evidence}</span></td>
        <td><span style="font-size:0.8rem; color:var(--accent-blue);">${e.recommended_action}</span></td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Failed to load exceptions", err);
  }
}

// 7. Evaluation View
async function loadEvaluation() {
  try {
    const res = await fetch("/api/evaluation");
    const evalData = await res.json();
    const s = evalData.summary;

    document.getElementById("evalPrecision").textContent = `${(s.precision * 100).toFixed(1)}%`;
    document.getElementById("evalRecall").textContent = `${(s.recall * 100).toFixed(1)}%`;
    document.getElementById("evalF1").textContent = s.f1_score.toFixed(4);
    document.getElementById("evalTotalGT").textContent = s.total_ground_truth;

    document.getElementById("cmTP").textContent = s.true_positives;
    document.getElementById("cmFP").textContent = s.false_positives;
    document.getElementById("cmFN").textContent = s.false_negatives;

    // Breakdown table
    const bTable = document.getElementById("evalBreakdownTable");
    bTable.innerHTML = Object.entries(evalData.breakdown_by_issue_type).map(([itype, b]) => `
      <tr>
        <td><strong>${itype}</strong></td>
        <td><span class="badge badge-green">${b.tp}</span></td>
        <td><span class="badge ${b.fp > 0 ? 'badge-amber' : 'badge-blue'}">${b.fp}</span></td>
        <td><span class="badge ${b.fn > 0 ? 'badge-red' : 'badge-blue'}">${b.fn}</span></td>
        <td><strong>${(b.precision * 100).toFixed(1)}%</strong></td>
        <td><strong>${(b.recall * 100).toFixed(1)}%</strong></td>
        <td><strong style="color:var(--accent-blue);">${b.f1.toFixed(4)}</strong></td>
      </tr>
    `).join("");

    // Side-by-side verification table
    const compTable = document.getElementById("evalComparisonTable");
    const items = [...evalData.true_positives_sample, ...evalData.false_positives, ...evalData.false_negatives];
    compTable.innerHTML = items.map(item => `
      <tr>
        <td>
          <span class="badge ${item.status === 'TRUE_POSITIVE' ? 'badge-green' : (item.status === 'FALSE_POSITIVE' ? 'badge-amber' : 'badge-red')}">
            ${item.status}
          </span>
        </td>
        <td><strong>${item.issue_type}</strong></td>
        <td><code>${item.target_entity_id}</code></td>
        <td><code>${item.seller_id}</code></td>
        <td>$${item.financial_impact.toFixed(2)}</td>
        <td><span style="font-size:0.8rem;">${item.evidence}</span></td>
        <td><span style="font-size:0.8rem; color:var(--text-muted);">${item.ground_truth_desc}</span></td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Failed to load evaluation data", err);
  }
}

// 8. Event Logs
async function loadEvents(page = 1) {
  eventPage = page;
  const entityType = document.getElementById("eventTypeFilter").value;
  const entityId = document.getElementById("eventEntityIdInput").value.trim();

  try {
    const res = await fetch(`/api/events?page=${page}&limit=50&entity_type=${entityType}&entity_id=${encodeURIComponent(entityId)}`);
    const data = await res.json();
    const events = data.items ? data.items : data;
    const total = data.total !== undefined ? data.total : events.length;
    const totalPages = data.total_pages !== undefined ? data.total_pages : 1;

    const tbody = document.getElementById("eventsTable");
    tbody.innerHTML = events.map(e => `
      <tr>
        <td><code>${e.event_id}</code></td>
        <td><span class="badge badge-blue">${e.entity_type}</span></td>
        <td><code>${e.entity_id}</code></td>
        <td><strong>${e.event_type}</strong></td>
        <td>${e.old_state ? `<span class="badge badge-amber">${e.old_state}</span>` : '-'}</td>
        <td>${e.new_state ? `<span class="badge badge-green">${e.new_state}</span>` : '-'}</td>
        <td><span class="badge badge-purple">${e.actor}</span></td>
        <td>${e.created_at}</td>
        <td><code style="font-size:0.75rem;">${e.payload_json || '{}'}</code></td>
      </tr>
    `).join("");

    renderPaginationControls("eventPagination", eventPage, totalPages, total, "loadEvents");
  } catch (err) {
    console.error("Failed to load events", err);
  }
}

// 9. Exports
async function triggerExport(fmt) {
  const statusBox = document.getElementById("exportStatusBox");
  const logContent = document.getElementById("exportOutputContent");
  statusBox.style.display = "block";
  logContent.textContent = `Exporting ${fmt.toUpperCase()} files... Please wait.`;

  try {
    const res = await fetch(`/api/export/${fmt}`);
    const data = await res.json();
    logContent.textContent = JSON.stringify(data, null, 2);
  } catch (err) {
    logContent.textContent = `Export error: ${err.message}`;
  }
}

// Modal controls
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.add("active");
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) modal.classList.remove("active");
}

// 6. Exception Queue
async function loadExceptions() {
  try {
    const res = await fetch("/api/exceptions");
    const data = await res.json();
    const tbody = document.getElementById("exceptionsTable");
    document.getElementById("badgeExceptions").textContent = data.count;

    tbody.innerHTML = data.exceptions.map(e => `
      <tr>
        <td><code>${e.exception_id}</code></td>
        <td><span class="badge ${e.severity === 'CRITICAL' ? 'badge-red' : 'badge-amber'}">${e.severity}</span></td>
        <td><strong>${e.issue_type}</strong></td>
        <td><code>${e.target_entity_type}: ${e.target_entity_id}</code></td>
        <td><code>${e.seller_id}</code></td>
        <td><strong style="color:var(--accent-red);">$${e.financial_impact.toFixed(2)}</strong></td>
        <td><span style="font-size:0.8rem;">${e.rule_violated}</span></td>
        <td><span style="font-size:0.8rem; color:var(--text-muted);">${e.evidence}</span></td>
        <td><span style="font-size:0.8rem; color:var(--accent-blue);">${e.recommended_action}</span></td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Failed to load exceptions", err);
  }
}

// 7. Evaluation View
async function loadEvaluation() {
  try {
    const res = await fetch("/api/evaluation");
    const evalData = await res.json();
    const s = evalData.summary;

    document.getElementById("evalPrecision").textContent = `${(s.precision * 100).toFixed(1)}%`;
    document.getElementById("evalRecall").textContent = `${(s.recall * 100).toFixed(1)}%`;
    document.getElementById("evalF1").textContent = s.f1_score.toFixed(4);
    document.getElementById("evalTotalGT").textContent = s.total_ground_truth;

    document.getElementById("cmTP").textContent = s.true_positives;
    document.getElementById("cmFP").textContent = s.false_positives;
    document.getElementById("cmFN").textContent = s.false_negatives;

    // Breakdown table
    const bTable = document.getElementById("evalBreakdownTable");
    bTable.innerHTML = Object.entries(evalData.breakdown_by_issue_type).map(([itype, b]) => `
      <tr>
        <td><strong>${itype}</strong></td>
        <td><span class="badge badge-green">${b.tp}</span></td>
        <td><span class="badge ${b.fp > 0 ? 'badge-amber' : 'badge-blue'}">${b.fp}</span></td>
        <td><span class="badge ${b.fn > 0 ? 'badge-red' : 'badge-blue'}">${b.fn}</span></td>
        <td><strong>${(b.precision * 100).toFixed(1)}%</strong></td>
        <td><strong>${(b.recall * 100).toFixed(1)}%</strong></td>
        <td><strong style="color:var(--accent-blue);">${b.f1.toFixed(4)}</strong></td>
      </tr>
    `).join("");

    // Side-by-side verification table
    const compTable = document.getElementById("evalComparisonTable");
    const items = [...evalData.true_positives_sample, ...evalData.false_positives, ...evalData.false_negatives];
    compTable.innerHTML = items.map(item => `
      <tr>
        <td>
          <span class="badge ${item.status === 'TRUE_POSITIVE' ? 'badge-green' : (item.status === 'FALSE_POSITIVE' ? 'badge-amber' : 'badge-red')}">
            ${item.status}
          </span>
        </td>
        <td><strong>${item.issue_type}</strong></td>
        <td><code>${item.target_entity_id}</code></td>
        <td><code>${item.seller_id}</code></td>
        <td>$${item.financial_impact.toFixed(2)}</td>
        <td><span style="font-size:0.8rem;">${item.evidence}</span></td>
        <td><span style="font-size:0.8rem; color:var(--text-muted);">${item.ground_truth_desc}</span></td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Failed to load evaluation data", err);
  }
}


