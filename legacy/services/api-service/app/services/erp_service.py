"""ERP System service with predefined configurations."""
from typing import List, Dict, Any, Optional


class ERPService:
    """Service for ERP system configurations."""
    
    # ERP System Configurations
    ERP_SYSTEMS = {
        "sap": {
            "name": "SAP",
            "description": "SAP ERP Financial Accounting",
            "fields": [
                {"id": "account_number", "name": "Account Number", "type": "string", "required": True},
                {"id": "account_name", "name": "Account Name", "type": "string", "required": True},
                {"id": "account_type", "name": "Account Type", "type": "string", "required": True},
                {"id": "parent_account", "name": "Parent Account", "type": "string", "required": False},
                {"id": "currency", "name": "Currency", "type": "string", "required": False},
                {"id": "cost_center", "name": "Cost Center", "type": "string", "required": False},
                {"id": "profit_center", "name": "Profit Center", "type": "string", "required": False},
                {"id": "company_code", "name": "Company Code", "type": "string", "required": False},
            ]
        },
        "oracle_netsuite": {
            "name": "Oracle NetSuite",
            "description": "Oracle NetSuite Cloud ERP",
            "fields": [
                {"id": "account_number", "name": "Account Number", "type": "string", "required": True},
                {"id": "account_name", "name": "Account Name", "type": "string", "required": True},
                {"id": "account_type", "name": "Type", "type": "string", "required": True},
                {"id": "subaccount_of", "name": "Subaccount Of", "type": "string", "required": False},
                {"id": "currency", "name": "Currency", "type": "string", "required": False},
                {"id": "department", "name": "Department", "type": "string", "required": False},
                {"id": "class_field", "name": "Class", "type": "string", "required": False},
                {"id": "location", "name": "Location", "type": "string", "required": False},
            ]
        },
        "microsoft_dynamics": {
            "name": "Microsoft Dynamics 365",
            "description": "Microsoft Dynamics 365 Finance",
            "fields": [
                {"id": "main_account", "name": "Main Account", "type": "string", "required": True},
                {"id": "account_name", "name": "Name", "type": "string", "required": True},
                {"id": "main_account_type", "name": "Main Account Type", "type": "string", "required": True},
                {"id": "main_account_category", "name": "Main Account Category", "type": "string", "required": False},
                {"id": "currency_code", "name": "Currency Code", "type": "string", "required": False},
                {"id": "financial_dimension", "name": "Financial Dimension", "type": "string", "required": False},
                {"id": "legal_entity", "name": "Legal Entity", "type": "string", "required": False},
            ]
        },
        "quickbooks": {
            "name": "QuickBooks",
            "description": "Intuit QuickBooks Online/Desktop",
            "fields": [
                {"id": "account_number", "name": "Number", "type": "string", "required": False},
                {"id": "account_name", "name": "Name", "type": "string", "required": True},
                {"id": "account_type", "name": "Type", "type": "string", "required": True},
                {"id": "detail_type", "name": "Detail Type", "type": "string", "required": False},
                {"id": "description", "name": "Description", "type": "string", "required": False},
                {"id": "balance", "name": "Balance", "type": "number", "required": False},
            ]
        },
        "sage": {
            "name": "Sage Intacct",
            "description": "Sage Intacct Cloud Accounting",
            "fields": [
                {"id": "account_no", "name": "Account No", "type": "string", "required": True},
                {"id": "title", "name": "Title", "type": "string", "required": True},
                {"id": "account_type", "name": "Account Type", "type": "string", "required": True},
                {"id": "normal_balance", "name": "Normal Balance", "type": "string", "required": False},
                {"id": "category", "name": "Category", "type": "string", "required": False},
                {"id": "department_id", "name": "Department ID", "type": "string", "required": False},
            ]
        },
        "xero": {
            "name": "Xero",
            "description": "Xero Cloud Accounting",
            "fields": [
                {"id": "code", "name": "Code", "type": "string", "required": False},
                {"id": "name", "name": "Name", "type": "string", "required": True},
                {"id": "type", "name": "Type", "type": "string", "required": True},
                {"id": "tax_type", "name": "Tax Type", "type": "string", "required": False},
                {"id": "description", "name": "Description", "type": "string", "required": False},
                {"id": "bank_account_number", "name": "Bank Account Number", "type": "string", "required": False},
            ]
        }
    }
    
    # Account Type Mappings between ERP systems
    ACCOUNT_TYPE_MAPPINGS = {
        "quickbooks_to_xero": {
            "Bank": "BANK",
            "Accounts Receivable": "CURRENT",
            "Other Current Assets": "CURRENT",
            "Fixed Assets": "FIXED",
            "Accounts Payable": "CURRLIAB",
            "Credit Card": "CURRLIAB",
            "Other Current Liability": "CURRLIAB",
            "Long Term Liability": "TERMLIAB",
            "Equity": "EQUITY",
            "Income": "REVENUE",
            "Other Income": "OTHERINCOME",
            "Cost of Goods Sold": "DIRECTCOSTS",
            "Expenses": "OVERHEADS",
            "Other Expense": "EXPENSE"
        },
        "sap_to_oracle_netsuite": {
            "Asset": "Other Current Asset",
            "Liability": "Other Current Liability",
            "Equity": "Equity",
            "Revenue": "Income",
            "Expense": "Expense"
        },
        "xero_to_quickbooks": {
            "BANK": "Bank",
            "CURRENT": "Other Current Assets",
            "FIXED": "Fixed Assets",
            "CURRLIAB": "Other Current Liability",
            "TERMLIAB": "Long Term Liability",
            "EQUITY": "Equity",
            "REVENUE": "Income",
            "OTHERINCOME": "Other Income",
            "DIRECTCOSTS": "Cost of Goods Sold",
            "OVERHEADS": "Expenses",
            "EXPENSE": "Other Expense"
        }
    }
    
    # Target ERP Account Types
    TARGET_ACCOUNT_TYPES = {
        "xero": ["BANK", "CURRENT", "FIXED", "INVENTORY", "NONCURRENT", "PREPAYMENT", "CURRLIAB", "TERMLIAB", "LIABILITY", "EQUITY", "REVENUE", "OTHERINCOME", "DIRECTCOSTS", "OVERHEADS", "EXPENSE", "DEPRECIATN"],
        "oracle_netsuite": ["Bank", "Accounts Receivable", "Other Current Asset", "Fixed Asset", "Other Asset", "Accounts Payable", "Credit Card", "Other Current Liability", "Long Term Liability", "Equity", "Income", "Other Income", "Cost of Goods Sold", "Expense", "Other Expense"],
        "sap": ["Asset", "Liability", "Equity", "Revenue", "Expense"],
        "microsoft_dynamics": ["Asset", "Liability", "Equity", "Revenue", "Expense"],
        "quickbooks": ["Bank", "Accounts Receivable", "Other Current Assets", "Fixed Assets", "Other Assets", "Accounts Payable", "Credit Card", "Other Current Liability", "Long Term Liability", "Equity", "Income", "Other Income", "Cost of Goods Sold", "Expenses", "Other Expense"],
        "sage": ["Asset", "Liability", "Equity", "Revenue", "Expense"]
    }
    
    # Sample COA Data for each ERP system (abbreviated for brevity)
    SAMPLE_COA_DATA = {
        "sap": [
            {"Account Number": "1000", "Account Name": "Cash and Cash Equivalents", "Account Type": "Asset", "Parent Account": "", "Currency": "USD", "Cost Center": "CC001", "Profit Center": "PC001", "Company Code": "1000"},
            {"Account Number": "1100", "Account Name": "Accounts Receivable", "Account Type": "Asset", "Parent Account": "1000", "Currency": "USD", "Cost Center": "CC001", "Profit Center": "PC001", "Company Code": "1000"},
            {"Account Number": "1200", "Account Name": "Inventory", "Account Type": "Asset", "Parent Account": "", "Currency": "USD", "Cost Center": "CC002", "Profit Center": "PC001", "Company Code": "1000"},
            {"Account Number": "2000", "Account Name": "Accounts Payable", "Account Type": "Liability", "Parent Account": "", "Currency": "USD", "Cost Center": "CC001", "Profit Center": "PC001", "Company Code": "1000"},
            {"Account Number": "3000", "Account Name": "Share Capital", "Account Type": "Equity", "Parent Account": "", "Currency": "USD", "Cost Center": "", "Profit Center": "PC001", "Company Code": "1000"},
            {"Account Number": "4000", "Account Name": "Sales Revenue", "Account Type": "Revenue", "Parent Account": "", "Currency": "USD", "Cost Center": "CC005", "Profit Center": "PC001", "Company Code": "1000"},
            {"Account Number": "5000", "Account Name": "Cost of Goods Sold", "Account Type": "Expense", "Parent Account": "", "Currency": "USD", "Cost Center": "CC002", "Profit Center": "PC001", "Company Code": "1000"},
        ],
        "quickbooks": [
            {"Number": "1000", "Name": "Checking", "Type": "Bank", "Detail Type": "Checking", "Description": "Main business checking account", "Balance": 50000.00},
            {"Number": "1300", "Name": "Accounts Receivable", "Type": "Accounts Receivable", "Detail Type": "Accounts Receivable", "Description": "Money owed by customers", "Balance": 15000.00},
            {"Number": "1400", "Name": "Inventory", "Type": "Other Current Assets", "Detail Type": "Inventory", "Description": "Products for sale", "Balance": 30000.00},
            {"Number": "2000", "Name": "Accounts Payable", "Type": "Accounts Payable", "Detail Type": "Accounts Payable", "Description": "Money owed to vendors", "Balance": 12000.00},
            {"Number": "3000", "Name": "Owner's Equity", "Type": "Equity", "Detail Type": "Owner's Equity", "Description": "Owner's investment", "Balance": 100000.00},
            {"Number": "4000", "Name": "Sales Revenue", "Type": "Income", "Detail Type": "Sales of Product Income", "Description": "Revenue from product sales", "Balance": 0.00},
            {"Number": "5000", "Name": "Cost of Goods Sold", "Type": "Cost of Goods Sold", "Detail Type": "Supplies & Materials - COGS", "Description": "Direct costs of products sold", "Balance": 0.00},
        ],
        "xero": [
            {"Code": "090", "Name": "Petty Cash", "Type": "BANK", "Tax Type": "NONE", "Description": "Office petty cash fund", "Bank Account Number": ""},
            {"Code": "200", "Name": "Sales", "Type": "REVENUE", "Tax Type": "OUTPUT2", "Description": "Income from sales", "Bank Account Number": ""},
            {"Code": "310", "Name": "Cost of Goods Sold", "Type": "DIRECTCOSTS", "Tax Type": "INPUT2", "Description": "Direct costs of products", "Bank Account Number": ""},
            {"Code": "400", "Name": "Advertising", "Type": "OVERHEADS", "Tax Type": "INPUT2", "Description": "Marketing and advertising costs", "Bank Account Number": ""},
            {"Code": "610", "Name": "Accounts Receivable", "Type": "CURRENT", "Tax Type": "NONE", "Description": "Trade debtors", "Bank Account Number": ""},
            {"Code": "800", "Name": "Accounts Payable", "Type": "CURRLIAB", "Tax Type": "NONE", "Description": "Trade creditors", "Bank Account Number": ""},
            {"Code": "960", "Name": "Retained Earnings", "Type": "EQUITY", "Tax Type": "NONE", "Description": "Accumulated profits", "Bank Account Number": ""},
        ],
        "oracle_netsuite": [],
        "microsoft_dynamics": [],
        "sage": []
    }
    
    def get_all_systems(self) -> List[Dict[str, Any]]:
        """Get all ERP systems with their configurations."""
        return [
            {"id": key, **value}
            for key, value in self.ERP_SYSTEMS.items()
        ]
    
    def get_system(self, erp_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific ERP system configuration."""
        if erp_id not in self.ERP_SYSTEMS:
            return None
        return {"id": erp_id, **self.ERP_SYSTEMS[erp_id]}
    
    def get_account_types(self, erp_id: str) -> List[str]:
        """Get available account types for an ERP system."""
        return self.TARGET_ACCOUNT_TYPES.get(erp_id, [])
    
    def get_type_mapping(self, source_erp: str, target_erp: str) -> Dict[str, str]:
        """Get account type mappings between two ERP systems."""
        mapping_key = f"{source_erp}_to_{target_erp}"
        return self.ACCOUNT_TYPE_MAPPINGS.get(mapping_key, {})
    
    def get_sample_data(self, erp_id: str) -> List[Dict[str, Any]]:
        """Get sample COA data for an ERP system."""
        return self.SAMPLE_COA_DATA.get(erp_id, [])


# Singleton instance
erp_service = ERPService()
