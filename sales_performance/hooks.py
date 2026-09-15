app_name = "sales_performance"
app_title = "Sales Performance"
app_publisher = "Taimoor"
app_description = "Advanced sales target planning, pricing, achievement, and incentive architecture on top of ERPNext"
app_email = "taimoor986@gmail.com"
app_license = "mit"
app_logo_url = "/assets/sales_performance/images/sales-performance-logo.png"
app_home = "/app/sales-performance"

required_apps = ["erpnext"]

app_include_css = ["/assets/sales_performance/css/desktop_icon.css"]

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
