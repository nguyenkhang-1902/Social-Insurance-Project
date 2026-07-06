from sqlalchemy import Column, Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Employee(Base):
    __tablename__ = "employee"

    emp_id = Column(String(50), primary_key=True, index=True)
    full_name = Column(String(200), nullable=False)
    join_date = Column(Date, nullable=True)
    birth_date = Column(Date, nullable=True)
    social_no = Column(String(100), nullable=True)
    social_date = Column(String(100), nullable=True)  # PHASE 25: Changed from Date to String to preserve date format
    current_status = Column(String(50), nullable=False, default="Active")
    resign_date = Column(Date, nullable=True)
    current_salary = Column(Float, nullable=False, default=0.0)

    payroll_history = relationship(
        "PayrollHistory",
        back_populates="employee",
        cascade="all, delete-orphan",
    )


class PayrollHistory(Base):
    __tablename__ = "payroll_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    emp_id = Column(String(50), ForeignKey("employee.emp_id"), nullable=False, index=True)
    record_month = Column(Integer, nullable=False)
    record_year = Column(Integer, nullable=False)
    base_salary = Column(Float, nullable=False, default=0.0)
    status_in_month = Column(String(50), nullable=False)
    resign_date = Column(Date, nullable=True)
    bhxh_val = Column(String(100), nullable=True)
    bhyt_val = Column(String(100), nullable=True)
    bhtn_val = Column(String(100), nullable=True)
    bhbnn_val = Column(String(100), nullable=True)

    employee = relationship("Employee", back_populates="payroll_history")
