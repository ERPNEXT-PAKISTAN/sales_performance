app_name = "sales_performance"
app_title = "Sales Performance"
app_publisher = "Taimoor"
app_description = "Advanced sales target planning, pricing, achievement, and incentive architecture on top of ERPNext"
app_email = "taimoor986@gmail.com"
app_license = "mit"
app_logo_url = "/assets/sales_performance/images/sales-performance-logo.png"
app_home = "/app/sales-performance"

required_apps = ["erpnext"]

app_include_css = [
	"/assets/sales_performance/css/desktop_icon.css",
	"/assets/sales_performance/css/indicators.css",
	"/assets/sales_performance/css/desk_dashboard.css",
]
app_include_js = [
	"/assets/sales_performance/js/desktop_icon.js",
	"/assets/sales_performance/js/sp_runtime.js",
	"/assets/sales_performance/js/sales_views.js",
]

after_install = "sales_performance.install.after_install"
after_migrate = "sales_performance.install.after_migrate"
boot_session = "sales_performance.install.boot_session"

add_to_apps_screen = [
	{
		"name": "sales_performance",
		"logo": app_logo_url,
		"title": app_title,
		"route": app_home,
	}
]

doc_events = {
	"Payment Entry": {
		"on_submit": "sales_performance.sales_performance.doctype.sales_incentive_payout.sales_incentive_payout.on_payment_entry_submit",
		"on_cancel": "sales_performance.sales_performance.doctype.sales_incentive_payout.sales_incentive_payout.on_payment_entry_cancel",
	}
}

permission_query_conditions = {
    "Sales Target Planning": "sales_performance.services.access.query_conditions",
    "Sales Incentive Payout": "sales_performance.services.access.payout_query",
    "Sales Performance Update": "sales_performance.services.access.update_query",
}
has_permission = {
    name: "sales_performance.services.access.document_permission"
    for name in ("Sales Target Planning", "Sales Incentive Payout", "Sales Performance Update")
}
