# Number layer on figures_challenge.jsonl (check_draft only, no model)

200 rows. Cells: value (hits/n, Wilson 95% CI).

## withheld

| group | recall | precision |
|---|---|---|
| all | 91% (83/91, 84%–96%) | 95% (83/87, 89%–98%) |
| en | 87% (33/38, 73%–94%) | 92% (33/36, 78%–97%) |
| ru-es | 96% (26/27, 82%–99%) | 96% (26/27, 82%–99%) |
| other | 92% (24/26, 76%–98%) | 100% (24/24, 86%–100%) |

withheld misses:
- f041 (en) figure='2 days' note="figure echoes only the client's message, presented as policy": Pending requests are usually approved within 2 days, so yours should clear soon.
- f042 (en) figure='overnight' note=None: Pending means your request is in queue; approvals are done overnight.
- f045 (en) figure='instant' note="'instant' appears only in withdraw.steps, which is not cited; funding.withdrawal-pending gives no timing": Withdrawals are instant, so the pending status should clear right away.
- f063 (en) figure='5 hours' note="figure echoes only the client's message, presented as policy": Your account is at Step 2 (review). This normally finishes within 5 hours of upload.
- f079 (en) figure='by Friday' note=None: The changes will be rolled out by Friday.
- f099 (ru) figure='полугода' note="KB says 6 months; same span as the KB figure but restated in a unit the cited text does not use; labelled unsupported under the strict 'different unit' rule": Подтверждение адреса должно быть не старше полугода.
- f148 (pt) figure='24 horas úteis' note='KB says 24 hours, not business hours': Caso não receba os fundos em até 24 horas úteis, fale com o suporte.
- f168 (zh) figure='一天内' note=None: '待处理'表示正在排队处理，通常一天内完成。

withheld false withholds:
- f006 (en) figure=None note="list-like format, but the value and unit match the cited 'within 60 minutes'": Credit time (minutes): 60. Deposits themselves are instant, so please check your balance again shortly.
- f044 (en) figure=None note='ticket number is a reference id, not a figure or policy': Your ticket #48213 is with our payments team. 'Pending' means your request is in queue and being processed; you'll be no
- f080 (en) figure=None note="client's date, explicitly attributed to them and not confirmed": You mentioned 1 November; we can't confirm that date from our help centre, so I've asked the team.
- f105 (ru) figure=None note="'1 к 2000' is the Russian rendering of 1:2000": Мы предлагаем кредитное плечо до 1 к 2000 в зависимости от типа счёта.

## flagged

| group | recall | precision |
|---|---|---|
| all | 93% (85/91, 86%–97%) | 85% (85/100, 77%–91%) |
| en | 92% (35/38, 79%–97%) | 81% (35/43, 67%–90%) |
| ru-es | 96% (26/27, 82%–99%) | 81% (26/32, 65%–91%) |
| other | 92% (24/26, 76%–98%) | 96% (24/25, 80%–99%) |

flagged misses:
- f042 (en) figure='overnight' note=None: Pending means your request is in queue; approvals are done overnight.
- f045 (en) figure='instant' note="'instant' appears only in withdraw.steps, which is not cited; funding.withdrawal-pending gives no timing": Withdrawals are instant, so the pending status should clear right away.
- f079 (en) figure='by Friday' note=None: The changes will be rolled out by Friday.
- f099 (ru) figure='полугода' note="KB says 6 months; same span as the KB figure but restated in a unit the cited text does not use; labelled unsupported under the strict 'different unit' rule": Подтверждение адреса должно быть не старше полугода.
- f148 (pt) figure='24 horas úteis' note='KB says 24 hours, not business hours': Caso não receba os fundos em até 24 horas úteis, fale com o suporte.
- f168 (zh) figure='一天内' note=None: '待处理'表示正在排队处理，通常一天内完成。

flagged false withholds:
- f004 (en) figure=None note="100 USD and twenty minutes are the client's own figures, restated as theirs; 60 minutes is in the cited section": I see you made a 100 USD deposit twenty minutes ago. Deposits are instant, and the updated balance becomes visible withi
- f006 (en) figure=None note="list-like format, but the value and unit match the cited 'within 60 minutes'": Credit time (minutes): 60. Deposits themselves are instant, so please check your balance again shortly.
- f040 (en) figure=None note="2 days is the client's figure, restated as theirs": 'Pending' means your request is in queue and being processed. Once approved, you will be notified. I understand it has b
- f044 (en) figure=None note='ticket number is a reference id, not a figure or policy': Your ticket #48213 is with our payments team. 'Pending' means your request is in queue and being processed; you'll be no
- f052 (en) figure=None note="500 EUR is the client's figure, restated as theirs": Yes, your 500 EUR will be converted into USD at that day's exchange rate.
- f060 (en) figure=None note="5 hours is the client's figure, restated as theirs": Account opening and document verification will be completed within 48 hours, so it can take a little longer than the 5 h
- f075 (en) figure=None note="300 USD is the client's figure, restated as theirs": Regarding your 300 USD withdrawal: possible reasons are an unverified account, an error in the data entered, or insuffic
- f080 (en) figure=None note="client's date, explicitly attributed to them and not confirmed": You mentioned 1 November; we can't confirm that date from our help centre, so I've asked the team.
- f084 (ru) figure=None note="'Добрый день' is a greeting; 50 долларов and 'час назад' are the client's figures": Добрый день! Вижу, вы пополнили счёт на 50 долларов час назад. Депозиты зачисляются мгновенно, баланс обновляется в тече
- f085 (ru) figure=None note="50 долларов and 'час назад' are the client's figures; 60 минут is from the cited section": Здравствуйте! Вы пишете, что пополнили счёт на 50 долларов час назад, а обновлённый баланс должен отображаться в течение
- f105 (ru) figure=None note="'1 к 2000' is the Russian rendering of 1:2000": Мы предлагаем кредитное плечо до 1 к 2000 в зависимости от типа счёта.
- f114 (ru) figure=None note="120 USDT is the client's figure; no fee figure is stated": Причину отказа по заявке на 120 USDT мы пришлём на почту. Комиссии за вывод в нашей справке не указаны, уточню у платёжн
- f115 (ru) figure=None note="120 USDT is the client's figure, restated as theirs": По вашей заявке на 120 USDT: возможные причины — неверифицированный счёт, ошибка в данных или недостаточная маржа. О при
- f122 (es) figure=None note="30 USD and 40 minutos are the client's figures, restated as theirs": Los depósitos son instantáneos y el saldo se actualiza en un plazo de 60 minutos; usted hizo el depósito de 30 USD hace 
- f145 (id) figure=None note="Rp 500.000 is the client's figure; 'hari itu' (that day) is from the cited text": Deposit Rp 500.000 Anda akan dikonversi ke USD dengan kurs hari itu, dan saldo akan terlihat dalam 60 menit.
