frappe.pages["sales-performance-overview"].on_page_load = function(wrapper) {
 const page = frappe.ui.make_app_page({parent:wrapper,title:__("Sales Performance Overview"),single_column:true});
 new sales_performance.SalesView(page, true);
};
