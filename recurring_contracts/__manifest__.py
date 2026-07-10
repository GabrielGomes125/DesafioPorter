{
    "name": "Recurring Contracts",
    "version": "19.0.1.0.0",
    "summary": "Gestão de contratos recorrentes",
    "description": "Módulo para gestão de contratos recorrentes.",
    "category": "Sales",
    "license": "LGPL-3",
    "author": "Gabriel Gomes",
    "depends": ["mail", "sale_management", "account", "product"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/recurring_contract_views.xml",
    ],
    "installable": True,
    "application": True,
}
