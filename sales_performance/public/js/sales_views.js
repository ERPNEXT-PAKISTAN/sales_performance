frappe.provide("sales_performance");
sales_performance.SalesView = class {
    constructor(page, manager = false) {
        this.page = page; this.manager = manager; this.tab = "Home"; this.filters = {}; this.sequence = 0;
        this.root = $('<div class="sp-sales-view"><div class="sp-sales-filters"></div><div class="sp-sales-content"></div></div>').appendTo(page.body);
        const fields = [["company", "Company", "Select", ""], ["fiscal_year", "Fiscal Year", "Select", ""],
            ["month", "Month", "Select", Array.from({length:12}, (_, i) => ({value:String(i+1),label:__(frappe.datetime.str_to_obj(`2026-${String(i+1).padStart(2,"0")}-01`).toLocaleString("en",{month:"long"}))}))],
            ["customer_group", "Customer Group", "Link", "Customer Group"]];
        if (!manager) fields.push(["sales_person", "Sales Person", "Select", ""]);
        fields.forEach(([fieldname,label,fieldtype,options]) => {
            this.filters[fieldname] = frappe.ui.form.make_control({parent:$('<div></div>').appendTo(this.root.find('.sp-sales-filters')),render_input:true,
                df:{fieldname,label:__(label),fieldtype,options,change:()=>{ if(this.ready){ clearTimeout(this.timer); this.timer=setTimeout(()=>fieldname==="company" ? this.load_people().then(()=>this.refresh()) : this.refresh(),180); } }}});
        });
        this.content = this.root.find('.sp-sales-content');
        page.set_primary_action(__("Refresh"),()=>this.refresh(),"refresh");
        if(!manager) page.add_inner_button(__("Ask Manager"),()=>this.ask());
        this.root.on('click','[data-tab]',e=>{this.tab=e.currentTarget.dataset.tab;this.render();});
        this.root.on('click','[data-month]',e=>this.filters.month.set_value(e.currentTarget.dataset.month));
        this.root.on('click','[data-ack]',e=>this.acknowledge(e.currentTarget.dataset.ack));
        this.root.on('click','[data-more-sales]',()=>this.more_sales());
        this.root.on('click','[data-report]',e=>this.report(e.currentTarget.dataset.report));
        this.root.on('click','[data-person]',e=>{frappe.route_options={...this.values(),sales_person:e.currentTarget.dataset.person,month:e.currentTarget.dataset.period};frappe.set_route('my-sales');});
        this.root.on('click','[data-payout]',()=>this.payout_dialog());
        this.root.on('click','[data-revision]',e=>this.revision(e.currentTarget.dataset.revision));
        this.mobileQuery = window.matchMedia('(max-width: 767px)');
        const closeSidebar = () => { if (this.mobileQuery.matches && this.root.is(':visible')) frappe.app?.sidebar?.close(); };
        this.mobileQuery.addEventListener('change', closeSidebar);
        closeSidebar();
        this.initialize();
    }
    esc(v){return frappe.utils.escape_html(String(v ?? ""));}
    n(v){return format_number(v || 0,null,0);}
    values(){return Object.fromEntries(Object.entries(this.filters).map(([k,f])=>[k,f.get_value()]));}
    async call(method,args){const r=await frappe.call({method:'sales_performance.services.personal_sales.'+method,args});return r.message;}
    async initialize(){
        try {
            const context=await this.call('get_context'); this.context=context;
            if(!context.mapped){this.content.html('<div class="sp-sales-empty">'+__('Your account is not linked to a Sales Person. Ask your administrator to link your Employee or create a Sales Performance Assignment.')+'</div>');return;}
            this.filters.company.df.options=context.companies;this.filters.company.refresh();
            this.filters.fiscal_year.df.options=context.fiscal_years.map(y=>y.name);this.filters.fiscal_year.refresh();
            const route=frappe.route_options || {};frappe.route_options=null;
            const today=frappe.datetime.get_today();
            const year=context.fiscal_years.find(y=>y.year_start_date<=today && y.year_end_date>=today) || context.fiscal_years[0];
            await this.filters.company.set_value(route.company || frappe.defaults.get_user_default('Company') || context.companies[0]);
            if(!context.companies.includes(this.filters.company.get_value()))await this.filters.company.set_value(context.companies[0]);
            await this.filters.fiscal_year.set_value(route.fiscal_year || year?.name || '');
            await this.filters.month.set_value(route.month || String(new Date().getMonth()+1));
            await this.filters.customer_group.set_value(route.customer_group === undefined ? 'Market' : route.customer_group);
            await this.load_people(route.sales_person);
            this.ready=true;this.refresh();
            this.autoRefresh = setInterval(()=>{if(this.root.is(':visible') && !document.hidden && !window.cur_dialog)this.refresh(true);},60000);
        }catch(e){this.content.html('<div class="sp-sales-empty">'+__('Unable to load your account. Check your assignment and try Refresh.')+'</div>');}
    }
    async load_people(person){
        if(this.manager)return;
        const people=await this.call('get_people',{company:this.filters.company.get_value()});
        const field=this.filters.sales_person;const previous=person || field.get_value();
        field.df.options=people;field.refresh();
        await field.set_value(people.includes(previous)?previous:people.length===1?people[0]:'');
        field.$wrapper.toggle(people.length!==1);
    }
    async refresh(silent=false){
        if(!this.ready)return this.initialize();
        const args=this.values();
        if(!args.company || !args.fiscal_year || !args.month || (!this.manager&&!args.sales_person)){
            this.content.html('<div class="sp-sales-empty">'+__('Select Company, Fiscal Year, Month and Sales Person to continue.')+'</div>');return;
        }
        const sequence=++this.sequence;if(!silent)this.content.html('<div class="sp-sales-empty">'+__('Loading your sales…')+'</div>');
        try{const data=await this.call(this.manager?'get_manager_data':'get_personal_data',args);if(sequence!==this.sequence)return;this.data=data;this.render();}
        catch(e){if(sequence===this.sequence)this.content.html('<div class="sp-sales-empty">'+__('Unable to load this view. Check your access and filters, then refresh.')+'</div>');}
    }
    badge(status){return `<span class="sp-sales-badge ${status==='Achieved'?'good':status==='Behind pace'?'bad':'warn'}">${this.esc(__(status))}</span>`;}
    card(label,value,report){return `<button type="button" class="sp-sales-card" ${report==='payout'?'data-payout="1"':report?`data-report="${report}"`:'data-tab="Targets"'}><span>${this.esc(__(label))}</span><strong>${this.n(value)}</strong></button>`;}
    render(){
        if(!this.data)return;
        const d=this.data;
        const meta=`<div class="sp-sales-meta"><span>${this.esc(d.sales_person || __('Assigned team'))}</span><span>${this.esc(this.filters.customer_group.get_value() || __('All customer groups'))}</span><span>${__('Updated')}: ${this.esc(frappe.datetime.str_to_user(d.updated_at))}</span><span>${d.provisional?__('Provisional targets included'):__('Approved targets')}</span></div>`;
        if(this.manager){this.content.html(meta+this.manager_view());return;}
        const tabs=['Home','Targets','Incentives','Sales','Updates'].map(t=>`<button type="button" data-tab="${t}" class="${this.tab===t?'active':''}">${__(t)}</button>`).join('');
        const renderers={Home:()=>this.home(),Targets:()=>this.targets(),Incentives:()=>this.incentives(),Sales:()=>this.sales(),Updates:()=>this.updates()};
        this.content.html(meta+`<div class="sp-sales-tabs" role="navigation" aria-label="${__('My Sales sections')}">${tabs}</div>`+renderers[this.tab]());
    }
    home(){
        const d=this.data,t=d.totals,p=d.pace;
        return `${!d.plans.length?`<div class="sp-sales-panel"><strong>${__('No approved target plan yet')}</strong><p>${__('Your invoice sales are available. Targets and incentive estimates will appear after your manager approves the plan.')}</p></div>`:''}<h3>${this.esc(d.month_label)} · ${this.esc(d.fiscal_year)}</h3>${this.badge(p.status)}
            <div class="sp-sales-cards">${this.card('Target amount',t.target_amount)}${this.card('Sales on target items',t.actual_amount)}${this.card('Net invoice sales',d.sales.totals.attributed_amount)}${this.card('Achievement %',t.amount_achievement_percent)}${this.card('Remaining amount',p.remaining)}${this.card(d.pay_on==='Qty'?'Estimated incentive units':'Estimated incentive amount',t.incentive_amount)}${this.card('Paid incentive amount',d.payouts.totals.paid)}</div>
            <div class="sp-sales-panel"><h3>${__('What remains')}</h3><p>${p.daily_needed===null?__('This month has ended.'):`${this.n(p.daily_needed)} ${this.esc(d.currency)} ${__('per calendar day needed')} · ${p.remaining_days} ${__('days remaining')}`}</p><div class="sp-sales-progress"><div style="width:${Math.max(0,Math.min(100,t.amount_achievement_percent||0))}%"></div></div><p class="sp-sales-small">${__('Targets and incentives cover planned items. Sales history shows your attributed invoice sales, including returns. Estimates can change until the payout is posted.')}</p></div>
            <div class="sp-sales-panel"><h3>${__('Monthly target and actual amount')}</h3><p class="sp-sales-small">${__('Blue: target · Green: actual. Tap a month to view it.')}</p>${this.months()}</div>
            <div class="sp-sales-panel"><h3>${__('Items needing attention')}</h3>${this.item_cards([...d.items].sort((a,b)=>b.amount_pace.remaining-a.amount_pace.remaining).slice(0,5))}</div>`;
    }
    months(){
        const max=Math.max(1,...this.data.monthly.flatMap(m=>[m.target_amount,m.actual_amount]));
        return '<div class="sp-sales-months">'+this.data.monthly.map(m=>`<button class="sp-sales-month" data-month="${m.month}">${this.esc(m.label.slice(0,3))}<div class="sp-sales-bars"><span style="height:${Math.max(0,m.target_amount/max*60)}px"></span><span class="actual" style="height:${Math.max(0,m.actual_amount/max*60)}px"></span></div><strong>${this.n(m.actual_amount)}</strong><span class="sp-sales-small">${this.n(m.amount_achievement_percent)}%</span></button>`).join('')+'</div>';
    }
    item_cards(items){
        if(!items.length)return `<p class="sp-sales-small">${__('No approved target items for these filters.')}</p>`;
        return items.map(i=>`<details class="sp-sales-item"><summary><span>${this.esc(i.item_name)}<small class="sp-sales-small d-block">${this.esc(i.territory)} · ${this.esc(i.customer_group)}</small></span>${this.badge(i.pace.status)}</summary><div class="sp-sales-values">${[['Target qty',i.target_qty],['Actual qty',i.actual_qty],['Remaining qty',i.pace.remaining],['Target amount',i.target_amount],['Actual amount',i.actual_amount],['Incentive',i.incentive_amount]].map(([k,v])=>`<div>${__(k)}<strong>${this.n(v)}</strong></div>`).join('')}</div><p class="sp-sales-small">${__('Quantity unit')}: ${this.esc(i.uom)} · ${__('Currency')}: ${this.esc(this.data.currency)} · ${__('Plan')}: ${this.esc(i.planning)}</p><p>${__('Surplus')}: ${this.n(i.surplus)} · ${__('Rate')}: ${this.n(i.incentive_rate_percent)}% · ${this.esc(i.incentive_band || __('No incentive earned'))}</p>${i.next_threshold?`<p>${__('Next incentive threshold')}: ${this.n(i.next_threshold)}%</p>`:''}<p class="sp-sales-small">${this.data.calculation_level==='Grouped'?__('The group earns the payout; eligible items receive an allocated share.'):__('Each item is evaluated against the configured incentive scheme.')}</p></details>`).join('');
    }
    targets(){
        const groups={};this.data.items.forEach(i=>(groups[i.item_group||__('Other')] ||= []).push(i));
        return Object.entries(groups).map(([name,items])=>`<details class="sp-sales-panel" open><summary><strong>${this.esc(name)}</strong> (${items.length})</summary><div class="mt-3">${this.item_cards(items)}</div></details>`).join('') || `<div class="sp-sales-empty">${__('No approved targets for this month.')}</div>`;
    }
    incentives(){const d=this.data,p=d.payouts.totals;return `<div class="sp-sales-cards">${this.card(d.pay_on==='Qty'?'Calculated incentive units':'Calculated incentive amount',d.totals.incentive_amount)}${this.card('Posted amount',p.accrued)}${this.card('Paid amount',p.paid)}${this.card('Unpaid amount',p.unpaid)}</div><p class="sp-sales-small">${__('Posted and paid values are money in')} ${this.esc(d.currency)}. ${__('Quantity rewards require a configured conversion rate before posting.')}</p><div class="sp-sales-panel"><h3>${__('Payment history for this month')}</h3>${this.payment_rows()}</div>${this.item_cards(d.items.filter(i=>i.incentive_amount>0))}`;}
    payment_rows(){return this.data.payouts.documents.map(p=>`<div class="sp-sales-event"><strong>${this.esc(p.name)} · ${this.n(p.total_incentive_amount)}</strong><p>${this.esc(p.payment_status)} · ${this.esc(p.posting_date)} ${p.paid_on?`· ${__('Paid on')} ${this.esc(p.paid_on)}`:''}</p></div>`).join('') || `<p class="sp-sales-small">${__('No posted or draft payout for this selection.')}</p>`;}
    sales(){return `<div class="sp-sales-panel"><h3>${__('My invoice sales')}</h3><p class="sp-sales-small">${__('Submitted invoices, net of returns. Amounts reflect only your Sales Team contribution.')}</p><p><strong>${this.n(this.data.sales.totals.attributed_amount)} ${this.esc(this.data.currency)}</strong> · ${this.data.sales.totals.invoice_count} ${__('invoices')} · ${__('Latest posting')}: ${this.esc(this.data.sales.totals.last_posting_date||'—')}</p><div class="sp-sales-list">${this.data.sales.rows.map(r=>`<div class="sp-sales-event"><strong>${this.esc(r.customer_name)} · ${this.n(r.attributed_amount)} ${this.esc(this.data.currency)}</strong><p>${this.esc(r.name)} · ${this.esc(r.posting_date)} ${r.is_return?this.badge('Return'):''}</p></div>`).join('') || __('No invoice sales for this month.')}</div>${this.data.sales.has_more?`<button class="btn btn-default mt-3" data-more-sales>${__('Load more')}</button>`:''}</div>`;}
    updates(){return `<div class="sp-sales-panel"><h3>${__('Approved targets and revisions')}</h3>${this.data.plans.map(p=>`<div class="sp-sales-event"><strong>${this.esc(p.name)} · v${p.planning_version}</strong><p>${__('Approved')}: ${this.esc(p.approved_on)} · ${p.erpnext_targets_synced_on?__('Targets synced'):__('Sync pending')}</p>${p.acknowledged?this.badge('Acknowledged'):this.data.can_acknowledge?`<button class="btn btn-default btn-sm" data-ack="${this.esc(p.name)}">${__('Acknowledge target')}</button>`:''}</div>`).join('') || __('No approved target updates.')}</div><div class="sp-sales-panel"><h3>${__('Questions and announcements')}</h3>${this.data.updates.map(u=>`<div class="sp-sales-event"><strong>${this.esc(u.subject)}</strong><p>${this.esc(u.message)}</p>${u.response?`<p><b>${__('Manager reply')}:</b> ${this.esc(u.response)}</p>`:''}<span class="sp-sales-small">${this.esc(u.status)} · ${this.esc(u.modified)}</span></div>`).join('') || __('No updates yet.')}</div><div class="sp-sales-panel"><h3>${__('Incentive updates')}</h3>${this.payment_rows()}</div>`;}
    async more_sales(){const d=this.data;const next=await this.call('get_personal_sales',{...this.values(),offset:d.sales.next_offset});d.sales={...next,rows:[...d.sales.rows,...next.rows]};this.render();}
    ask(){if(!this.data)return;frappe.prompt([{fieldname:'subject',label:__('Subject'),fieldtype:'Data',reqd:1},{fieldname:'message',label:__('Message'),fieldtype:'Small Text',reqd:1}],async v=>{await this.call('ask_question',{company:this.data.company,sales_person:this.data.sales_person,...v});this.tab='Updates';this.refresh();},__('Ask your manager'));}
    async acknowledge(planning){await this.call('acknowledge_plan',{company:this.data.company,sales_person:this.data.sales_person,planning});this.refresh();}
    report(name){frappe.route_options={...this.values(),period:'Monthly'};frappe.set_route('query-report',name);}
    payout_dialog(){
        const dialog=new frappe.ui.Dialog({title:__('Payouts for selected filters'),size:'large',fields:[{fieldname:'payouts',fieldtype:'HTML'}]});
        dialog.fields_dict.payouts.$wrapper.html(this.payment_rows()+(this.data.payouts.has_more?`<p>${__('Showing the latest 100 matching documents; totals include all matching documents.')}</p>`:''));dialog.show();
    }
    async revision(name){
        const data=await this.call('get_revision_changes',{name});
        const dialog=new frappe.ui.Dialog({title:__('Revision changes'),size:'extra-large',fields:[{fieldname:'changes',fieldtype:'HTML'}]});
        dialog.fields_dict.changes.$wrapper.html(`<p>${this.esc(data.previous)} → ${this.esc(data.current)} · ${data.total} ${__('changed rows')}</p><div style="overflow:auto;max-height:60vh"><table class="table"><thead><tr>${['Sales Person','Item','Old qty','New qty','Old rate','New rate','Reason'].map(t=>`<th>${__(t)}</th>`).join('')}</tr></thead><tbody>${data.rows.map(r=>`<tr>${[r.sales_person,r.item,this.n(r.old_qty),this.n(r.new_qty),this.n(r.old_rate),this.n(r.new_rate),r.reason].map(v=>`<td>${this.esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);dialog.show();
    }
    manager_view(){
        const d=this.data,t=d.totals,p=d.payouts.totals;
        const link=(doctype,name)=>`/app/${frappe.router.slug(doctype)}/${encodeURIComponent(name)}`;
        return `<div class="sp-sales-cards">${this.card('Target amount',t.target_amount,'Sales Target Achievement')}${this.card('Actual amount',t.actual_amount,'Sales Target Achievement')}${this.card('Achievement %',t.amount_achievement_percent,'Target Achievement Status')}${this.card('Remaining amount',Math.max(0,t.target_amount-t.actual_amount),'Sales Target Achievement')}${this.card(d.pay_on==='Qty'?'Calculated incentive units':'Calculated incentive amount',t.incentive_amount,'Sales Target Monthly Performance')}${this.card('Posted amount',p.accrued,'payout')}${this.card('Paid amount',p.paid,'payout')}${this.card('Unpaid amount',p.unpaid,'payout')}</div>
        <div class="sp-sales-panel"><h3>${__('Sales person achievement by month')}</h3><p class="sp-sales-small">${__('Amount achievement. Green: target reached. Amber: below target. —: no target. Tap a cell for personal detail.')}</p><div class="sp-sales-table-wrap"><table class="sp-sales-heatmap"><thead><tr><th>${__('Sales Person')}</th>${d.months.map(m=>`<th>${this.esc(m.slice(0,3))}</th>`).join('')}</tr></thead><tbody>${d.heatmap.map(p=>`<tr><th>${this.esc(p.sales_person)}<br>${this.badge(p.pace.status)}</th>${p.months.map((m,i)=>`<td><button class="${m.target_amount>0?(m.actual_amount>=m.target_amount?'achieved':'missed'):''}" data-person="${this.esc(p.sales_person)}" data-period="${i+1}">${m.target_amount>0?this.n(m.amount_achievement_percent)+'%':'—'}</button></td>`).join('')}</tr>`).join('')}</tbody></table></div></div>
        <div class="sp-sales-grid"><div class="sp-sales-panel"><h3>${__('Approval queue')}</h3>${d.queue.map(q=>`<div class="sp-sales-event"><a href="${link('Sales Target Planning',q.name)}">${this.esc(q.name)}</a><p>${this.esc(q.sales_person||__('Combined plan'))} · ${this.esc(q.status)} · v${q.planning_version}</p><p>${this.n(q.rows_requiring_review)} ${__('warnings')} · ${this.n(q.rows_overridden)} ${__('overrides')}</p><p class="sp-sales-small">${this.esc(q.summary_warnings)}</p>${q.previous_planning?`<button class="btn btn-default btn-sm" data-revision="${this.esc(q.name)}">${__('Compare revision')}</button>`:''}</div>`).join('') || __('No plans waiting.')}</div>
        <div class="sp-sales-panel"><h3>${__('Questions to answer')}</h3>${d.questions.map(q=>`<div class="sp-sales-event"><a href="${link('Sales Performance Update',q.name)}">${this.esc(q.subject)}</a><p>${this.esc(q.sales_person)}</p><p>${this.esc(q.message)}</p></div>`).join('') || __('No unanswered questions.')}<div class="sp-sales-toolbar"><a class="btn btn-default btn-sm" href="/app/sales-performance-update/new-sales-performance-update">${__('New announcement')}</a><a class="btn btn-default btn-sm" href="/app/sales-performance-assignment">${__('Access assignments')}</a></div></div></div>`;
    }
};
