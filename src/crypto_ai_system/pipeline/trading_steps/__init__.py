"""The trading stage decomposed into narrow, sequenced steps.

``TradingAgent.execute`` is the sequencer; each module here owns one step with
explicit inputs and a small result. The split exists so "which gates does this
entry path consume" is answerable by reading one file — see
``docs/architecture/design_trading_agent_split_and_context.md``.

    context.py      CycleInputs — everything a step needs, built once per cycle
    stage_router.py fail-closed execution-stage resolution (paper/testnet/live)
    lifecycle.py    pure order-lifecycle derivation            (M2)
    settlement.py   position settlement, 3 variants + S8       (M3)
    entry.py        single-book entry chain                    (M4)
    multibook.py    budget-bounded multibook entry walk        (M4)
"""
