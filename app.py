from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import os, secrets

app=Flask(__name__)
app.config['SECRET_KEY']=os.getenv('SECRET_KEY','dev-change-me')
app.config['SQLALCHEMY_DATABASE_URI']=os.getenv('DATABASE_URL','sqlite:///tradieflow.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS']=False
db=SQLAlchemy(app); login=LoginManager(app); login.login_view='login'
JOB_STATUSES=['New','Scheduled','In Progress','Completed','Cancelled']; ROLES=['Owner','Admin','Worker']

class Business(db.Model):
    id=db.Column(db.Integer,primary_key=True); name=db.Column(db.String(140),nullable=False); trade=db.Column(db.String(80),default='General Services'); booking_slug=db.Column(db.String(80),unique=True,index=True); created_at=db.Column(db.DateTime,default=datetime.utcnow)
class User(UserMixin,db.Model):
    id=db.Column(db.Integer,primary_key=True); business_id=db.Column(db.Integer,db.ForeignKey('business.id'),nullable=False,index=True); email=db.Column(db.String(160),unique=True,nullable=False); password=db.Column(db.String(255),nullable=False); name=db.Column(db.String(120),nullable=False); role=db.Column(db.String(20),default='Owner')
class Customer(db.Model):
    id=db.Column(db.Integer,primary_key=True); business_id=db.Column(db.Integer,db.ForeignKey('business.id'),nullable=False,index=True); name=db.Column(db.String(140),nullable=False); phone=db.Column(db.String(50),default=''); email=db.Column(db.String(160),default=''); address=db.Column(db.String(255),default=''); notes=db.Column(db.Text,default=''); created_at=db.Column(db.DateTime,default=datetime.utcnow)
class Service(db.Model):
    id=db.Column(db.Integer,primary_key=True); business_id=db.Column(db.Integer,db.ForeignKey('business.id'),nullable=False,index=True); name=db.Column(db.String(120),nullable=False); price=db.Column(db.Float,default=0); duration=db.Column(db.Integer,default=60); active=db.Column(db.Boolean,default=True)
class Job(db.Model):
    id=db.Column(db.Integer,primary_key=True); business_id=db.Column(db.Integer,db.ForeignKey('business.id'),nullable=False,index=True); customer_id=db.Column(db.Integer,db.ForeignKey('customer.id'),nullable=False,index=True); service_id=db.Column(db.Integer,db.ForeignKey('service.id'),nullable=True); worker_id=db.Column(db.Integer,db.ForeignKey('user.id'),nullable=True,index=True); description=db.Column(db.Text,default=''); address=db.Column(db.String(255),default=''); start_at=db.Column(db.DateTime,nullable=False,index=True); duration=db.Column(db.Integer,default=60); status=db.Column(db.String(30),default='New',index=True); estimate=db.Column(db.Float,default=0); final_price=db.Column(db.Float,default=0); notes=db.Column(db.Text,default=''); source=db.Column(db.String(30),default='Internal'); created_at=db.Column(db.DateTime,default=datetime.utcnow)
class Invoice(db.Model):
    id=db.Column(db.Integer,primary_key=True); business_id=db.Column(db.Integer,db.ForeignKey('business.id'),nullable=False,index=True); job_id=db.Column(db.Integer,db.ForeignKey('job.id'),nullable=False,index=True); subtotal=db.Column(db.Float,default=0); gst=db.Column(db.Float,default=0); total=db.Column(db.Float,default=0); paid=db.Column(db.Boolean,default=False,index=True); issued_at=db.Column(db.Date,default=date.today); due_at=db.Column(db.Date,nullable=True)

@login.user_loader
def load(uid): return db.session.get(User,int(uid))
def biz(): return db.session.get(Business,current_user.business_id)
def money(v): return f'${v:,.2f}'
app.jinja_env.filters['money']=money

def conflict(business_id,worker_id,start_at,duration,ignore=None):
    if not worker_id: return False
    end=start_at+timedelta(minutes=duration)
    jobs=Job.query.filter_by(business_id=business_id,worker_id=worker_id).filter(Job.status.notin_(['Cancelled'])).all()
    for j in jobs:
        if ignore and j.id==ignore: continue
        jend=j.start_at+timedelta(minutes=j.duration)
        if start_at<jend and end>j.start_at: return True
    return False

def invoice_totals(subtotal):
    subtotal=round(float(subtotal or 0),2); gst=round(subtotal*.10,2); return subtotal,gst,round(subtotal+gst,2)

@app.route('/')
def index(): return redirect(url_for('dashboard')) if current_user.is_authenticated else redirect(url_for('login_view'))
@app.route('/register',methods=['GET','POST'])
def register():
    if request.method=='POST':
        email=request.form['email'].strip().lower()
        if User.query.filter_by(email=email).first(): flash('Email already registered.'); return redirect(url_for('register'))
        name=request.form['business'].strip(); slug=(name.lower().replace(' ','-')+'-'+secrets.token_hex(2))[:75]
        b=Business(name=name,trade=request.form.get('trade','General Services'),booking_slug=slug); db.session.add(b); db.session.flush()
        u=User(business_id=b.id,email=email,password=generate_password_hash(request.form['password']),name=request.form.get('name','Owner'),role='Owner'); db.session.add(u); db.session.commit(); login_user(u); return redirect(url_for('dashboard'))
    return render_template('auth.html',mode='Create business')
@app.route('/login',methods=['GET','POST'])
def login_view():
    if request.method=='POST':
        u=User.query.filter_by(email=request.form['email'].strip().lower()).first()
        if u and check_password_hash(u.password,request.form['password']): login_user(u); return redirect(url_for('dashboard'))
        flash('Invalid email or password.')
    return render_template('auth.html',mode='Sign in')
login.login_view='login_view'
@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('login_view'))

@app.route('/dashboard')
@login_required
def dashboard():
    today=date.today(); start=datetime.combine(today,datetime.min.time()); end=start+timedelta(days=1); jobs=Job.query.filter_by(business_id=current_user.business_id).all(); invoices=Invoice.query.filter_by(business_id=current_user.business_id).all()
    metrics={'today':sum(start<=j.start_at<end for j in jobs),'week':sum(start<=j.start_at<start+timedelta(days=7) for j in jobs),'revenue':sum(i.total for i in invoices if i.paid),'outstanding':sum(i.total for i in invoices if not i.paid),'customers':Customer.query.filter_by(business_id=current_user.business_id).count()}
    upcoming=Job.query.filter(Job.business_id==current_user.business_id,Job.start_at>=datetime.now()).order_by(Job.start_at).limit(7).all(); counts={s:sum(j.status==s for j in jobs) for s in JOB_STATUSES}; b=biz()
    return render_template('dashboard.html',m=metrics,upcoming=upcoming,counts=counts,b=b)

@app.route('/customers',methods=['GET','POST'])
@login_required
def customers():
    if request.method=='POST':
        f=request.form; db.session.add(Customer(business_id=current_user.business_id,name=f['name'],phone=f.get('phone',''),email=f.get('email',''),address=f.get('address',''),notes=f.get('notes',''))); db.session.commit(); flash('Customer added.')
    rows=Customer.query.filter_by(business_id=current_user.business_id).order_by(Customer.name).all(); return render_template('customers.html',rows=rows)

@app.route('/jobs',methods=['GET','POST'])
@login_required
def jobs():
    if request.method=='POST':
        f=request.form; start=datetime.fromisoformat(f['start_at']); duration=int(f.get('duration') or 60); worker=int(f['worker_id']) if f.get('worker_id') else None
        if conflict(current_user.business_id,worker,start,duration): flash('Scheduling conflict: that worker already has an overlapping job.'); return redirect(url_for('jobs'))
        j=Job(business_id=current_user.business_id,customer_id=int(f['customer_id']),service_id=int(f['service_id']) if f.get('service_id') else None,worker_id=worker,description=f.get('description',''),address=f.get('address',''),start_at=start,duration=duration,status=f.get('status','Scheduled'),estimate=float(f.get('estimate') or 0),notes=f.get('notes',''))
        db.session.add(j); db.session.commit(); flash('Job scheduled.')
    rows=Job.query.filter_by(business_id=current_user.business_id).order_by(Job.start_at.desc()).all(); cs=Customer.query.filter_by(business_id=current_user.business_id).all(); ss=Service.query.filter_by(business_id=current_user.business_id,active=True).all(); workers=User.query.filter_by(business_id=current_user.business_id).all(); return render_template('jobs.html',rows=rows,customers=cs,services=ss,workers=workers,statuses=JOB_STATUSES)

@app.post('/jobs/<int:jid>/status')
@login_required
def job_status(jid):
    j=Job.query.filter_by(id=jid,business_id=current_user.business_id).first_or_404(); s=request.form.get('status');
    if s in JOB_STATUSES: j.status=s; db.session.commit()
    return redirect(url_for('jobs'))

@app.route('/services',methods=['GET','POST'])
@login_required
def services():
    if request.method=='POST':
        db.session.add(Service(business_id=current_user.business_id,name=request.form['name'],price=float(request.form.get('price') or 0),duration=int(request.form.get('duration') or 60))); db.session.commit(); flash('Service added.')
    return render_template('services.html',rows=Service.query.filter_by(business_id=current_user.business_id).all())

@app.route('/team',methods=['GET','POST'])
@login_required
def team():
    if current_user.role not in ['Owner','Admin']: flash('Owner/Admin access required.'); return redirect(url_for('dashboard'))
    if request.method=='POST':
        email=request.form['email'].strip().lower()
        if not User.query.filter_by(email=email).first(): db.session.add(User(business_id=current_user.business_id,email=email,password=generate_password_hash(request.form['password']),name=request.form['name'],role=request.form.get('role','Worker'))); db.session.commit(); flash('Team member added.')
    return render_template('team.html',rows=User.query.filter_by(business_id=current_user.business_id).all(),roles=ROLES)

@app.route('/invoices',methods=['GET','POST'])
@login_required
def invoices():
    if request.method=='POST':
        j=Job.query.filter_by(id=int(request.form['job_id']),business_id=current_user.business_id).first_or_404(); sub,gst,total=invoice_totals(float(request.form.get('subtotal') or j.final_price or j.estimate)); db.session.add(Invoice(business_id=current_user.business_id,job_id=j.id,subtotal=sub,gst=gst,total=total,due_at=date.today()+timedelta(days=14))); db.session.commit(); flash('Invoice created with 10% GST.')
    rows=Invoice.query.filter_by(business_id=current_user.business_id).order_by(Invoice.id.desc()).all(); jobs=Job.query.filter_by(business_id=current_user.business_id).all(); return render_template('invoices.html',rows=rows,jobs=jobs)
@app.post('/invoices/<int:iid>/paid')
@login_required
def invoice_paid(iid):
    i=Invoice.query.filter_by(id=iid,business_id=current_user.business_id).first_or_404(); i.paid=not i.paid; db.session.commit(); return redirect(url_for('invoices'))

@app.route('/book/<slug>',methods=['GET','POST'])
def booking(slug):
    b=Business.query.filter_by(booking_slug=slug).first_or_404(); services=Service.query.filter_by(business_id=b.id,active=True).all()
    if request.method=='POST':
        f=request.form; c=Customer.query.filter_by(business_id=b.id,email=f.get('email','')).first() if f.get('email') else None
        if not c: c=Customer(business_id=b.id,name=f['name'],phone=f.get('phone',''),email=f.get('email',''),address=f.get('address','')); db.session.add(c); db.session.flush()
        s=Service.query.filter_by(id=int(f['service_id']),business_id=b.id).first_or_404(); start=datetime.fromisoformat(f['start_at']); j=Job(business_id=b.id,customer_id=c.id,service_id=s.id,description=f.get('notes',''),address=f.get('address',''),start_at=start,duration=s.duration,status='New',estimate=s.price,source='Public booking'); db.session.add(j); db.session.commit(); return render_template('booking_success.html',b=b,j=j)
    return render_template('booking.html',b=b,services=services)

@app.route('/seed')
@login_required
def seed():
    bid=current_user.business_id
    if not Customer.query.filter_by(business_id=bid).first():
        ss=[Service(business_id=bid,name='Call-out & inspection',price=120,duration=60),Service(business_id=bid,name='Standard service',price=220,duration=90),Service(business_id=bid,name='Major repair',price=480,duration=180)]; db.session.add_all(ss); db.session.flush()
        cs=[Customer(business_id=bid,name='Sarah Nguyen',phone='0400 111 222',email='sarah@example.com',address='Footscray VIC'),Customer(business_id=bid,name='Daniel Brooks',phone='0400 333 444',email='daniel@example.com',address='Sunshine VIC'),Customer(business_id=bid,name='Amina Hassan',phone='0400 555 666',email='amina@example.com',address='Essendon VIC')]; db.session.add_all(cs); db.session.flush()
        for n in range(5):
            j=Job(business_id=bid,customer_id=cs[n%3].id,service_id=ss[n%3].id,worker_id=current_user.id,description='Demo customer job',address=cs[n%3].address,start_at=datetime.now()+timedelta(days=n,hours=2),duration=ss[n%3].duration,status=['Scheduled','Scheduled','In Progress','Completed','New'][n],estimate=ss[n%3].price); db.session.add(j); db.session.flush()
            if n==3:
                sub,g,t=invoice_totals(j.estimate); db.session.add(Invoice(business_id=bid,job_id=j.id,subtotal=sub,gst=g,total=t,paid=True,due_at=date.today()+timedelta(days=14)))
        db.session.commit()
    return redirect(url_for('dashboard'))
@app.route('/health')
def health(): return jsonify(status='ok')
with app.app_context(): db.create_all()
if __name__=='__main__': app.run(debug=True,port=5002)
