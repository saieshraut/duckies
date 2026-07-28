frappe.provide("duckies");

frappe.pages["scan-customer"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Scan Customer"),
		single_column: true,
	});

	new duckies.ScanCustomer(page);
};

duckies.ScanCustomer = class ScanCustomer {
	constructor(page) {
		this.page = page;
		this.stream = null;
		this.raf = null;
		this.render();
	}

	render() {
		this.page.body.empty();
		$(`
			<div class="scan-customer-page">
				<div class="scan-input-row" style="max-width: 420px; margin-bottom: 16px;">
					<label class="text-muted small">
						${__("Scan with handheld scanner (or type the code) and press Enter")}
					</label>
					<input type="text" class="form-control scan-code-input"
						placeholder="${__("Waiting for scan...")}" autocomplete="off">
				</div>
				<div style="margin-bottom: 20px;">
					<button class="btn btn-default btn-sm scan-camera-btn">
						<i class="fa fa-camera"></i> ${__("Scan with Camera")}
					</button>
				</div>
				<div class="scan-camera-wrap" style="display:none; max-width: 420px; margin-bottom: 20px;">
					<video class="scan-video" style="width:100%; border-radius: 8px; background:#000;" playsinline></video>
					<canvas class="scan-canvas" style="display:none;"></canvas>
					<button class="btn btn-default btn-xs scan-camera-stop" style="margin-top:8px;">
						${__("Cancel")}
					</button>
				</div>
				<div class="scan-result" style="max-width: 420px;"></div>
			</div>
		`).appendTo(this.page.body);

		this.$input = this.page.body.find(".scan-code-input");
		this.$cameraWrap = this.page.body.find(".scan-camera-wrap");
		this.$video = this.page.body.find(".scan-video").get(0);
		this.$canvas = this.page.body.find(".scan-canvas").get(0);
		this.$result = this.page.body.find(".scan-result");

		this.$input.on("keydown", (e) => {
			if (e.key === "Enter") {
				const code = this.$input.val().trim();
				this.$input.val("");
				if (code) this.lookup(code);
			}
		});
		this.page.body.find(".scan-camera-btn").on("click", () => this.startCamera());
		this.page.body.find(".scan-camera-stop").on("click", () => this.stopCamera());

		this.$input.trigger("focus");
	}

	startCamera() {
		frappe.require(
			"/assets/duckies/js/jsqr.min.js",
			() => {
				this.$cameraWrap.show();
				navigator.mediaDevices
					.getUserMedia({ video: { facingMode: "environment" } })
					.then((stream) => {
						this.stream = stream;
						this.$video.srcObject = stream;
						this.$video.setAttribute("playsinline", true);
						this.$video.play();
						this.raf = requestAnimationFrame(() => this.scanFrame());
					})
					.catch(() => {
						this.$cameraWrap.hide();
						frappe.msgprint({
							title: __("Camera unavailable"),
							message: __("Couldn't access the camera. Use the scan input above with a handheld scanner instead."),
							indicator: "orange",
						});
					});
			}
		);
	}

	scanFrame() {
		if (!this.stream) return;
		const video = this.$video;
		if (video.readyState === video.HAVE_ENOUGH_DATA) {
			const canvas = this.$canvas;
			canvas.width = video.videoWidth;
			canvas.height = video.videoHeight;
			const ctx = canvas.getContext("2d");
			ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
			const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
			const code = window.jsQR(imageData.data, imageData.width, imageData.height);
			if (code && code.data) {
				this.stopCamera();
				this.lookup(code.data);
				return;
			}
		}
		this.raf = requestAnimationFrame(() => this.scanFrame());
	}

	stopCamera() {
		if (this.raf) cancelAnimationFrame(this.raf);
		this.raf = null;
		if (this.stream) {
			this.stream.getTracks().forEach((t) => t.stop());
			this.stream = null;
		}
		this.$cameraWrap.hide();
	}

	lookup(code) {
		frappe.call({
			method: "duckies.wallet.api.staff_lookup_customer",
			args: { code },
			freeze: true,
			callback: (r) => {
				if (r.message) this.showResult(r.message);
				this.$input.trigger("focus");
			},
			error: () => this.$input.trigger("focus"),
		});
	}

	showResult(c) {
		const fmt = (v) => format_currency(v, erpnext.get_currency(frappe.defaults.get_default("company")));
		this.$result.html(`
			<div class="scan-result-card" style="border:1px solid var(--border-color); border-radius:8px; padding:16px;">
				<div style="font-size: 18px; font-weight: 600;">${frappe.utils.escape_html(c.name || c.customer)}</div>
				<div class="text-muted small" style="margin-bottom:8px;">${frappe.utils.escape_html(c.customer)} ${c.mobile ? " · " + frappe.utils.escape_html(c.mobile) : ""}</div>
				<div style="display:flex; gap:24px; margin-top:8px;">
					<div><div class="text-muted small">${__("Wallet Balance")}</div><div style="font-size:16px; font-weight:600;">${fmt(c.wallet_balance)}</div></div>
					<div><div class="text-muted small">${__("Cash")}</div><div>${fmt(c.cash_balance)}</div></div>
					<div><div class="text-muted small">${__("Bonus")}</div><div>${fmt(c.bonus_balance)}</div></div>
				</div>
			</div>
		`);
	}
};
