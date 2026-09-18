frappe.pages["my-sales"].on_page_load = function(wrapper) {
 const page = frappe.ui.make_app_page({parent:wrapper,title:__("My Sales"),single_column:true});
 new sales_performance.SalesView(page, false);
};
