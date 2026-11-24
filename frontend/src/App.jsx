import { Route, Routes } from "react-router-dom";
import Layout from "./components/layout/Layout.jsx";
import ProtectedRoute from "./routes/ProtectedRoute.jsx";
import Home from "./pages/public/Home.jsx";
import AuthForm from "./pages/public/AuthForm.jsx";
import ComingSoon from "./pages/public/ComingSoon.jsx";
import ForgotPassword from "./pages/public/ForgotPassword.jsx";
import ResetPassword from "./pages/public/ResetPassword.jsx";
import VerifyEmail from "./pages/public/VerifyEmail.jsx";
import Account from "./pages/customer/Account.jsx";
import Shop from "./pages/public/Shop.jsx";
import ProductDetail from "./pages/public/ProductDetail.jsx";
import Wishlist from "./pages/customer/Wishlist.jsx";
import Cart from "./pages/customer/Cart.jsx";
import Checkout from "./pages/customer/Checkout.jsx";
import Orders from "./pages/customer/Orders.jsx";
import OrderDetail from "./pages/customer/OrderDetail.jsx";
import AdminShell from "./pages/admin/AdminShell.jsx";
import AdminDashboard from "./pages/admin/AdminDashboard.jsx";
import AdminUsers from "./pages/admin/AdminUsers.jsx";
import AdminCatalogue from "./pages/admin/AdminCatalogue.jsx";
import AdminReports from "./pages/admin/AdminReports.jsx";
import { About, Contact, Faq, Privacy, Returns, Terms } from "./pages/public/Policies.jsx";
import AdminProducts from "./pages/admin/AdminProducts.jsx";
import AdminOrders from "./pages/admin/AdminOrders.jsx";
import AiStylist from "./pages/customer/AiStylist.jsx";
import Wallet from "./pages/customer/Wallet.jsx";
import Subscriptions from "./pages/customer/Subscriptions.jsx";
import AdminCredits from "./pages/admin/AdminCredits.jsx";
import Stylists from "./pages/public/Stylists.jsx";
import StylistDetail from "./pages/public/StylistDetail.jsx";
import Consultations from "./pages/customer/Consultations.jsx";
import ConsultationDetail from "./pages/customer/ConsultationDetail.jsx";
import Rewards from "./pages/customer/Rewards.jsx";
import StylistDashboard from "./pages/stylist/StylistDashboard.jsx";
import StylistProfile from "./pages/stylist/StylistProfile.jsx";
import AdminStylists from "./pages/admin/AdminStylists.jsx";
import Dashboard from "./pages/customer/Dashboard.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="login" element={<AuthForm mode="login" />} />
        <Route path="register" element={<AuthForm mode="register" />} />
        <Route path="forgot-password" element={<ForgotPassword />} />
        <Route path="reset-password" element={<ResetPassword />} />
        <Route path="verify-email" element={<VerifyEmail />} />
        <Route path="shop" element={<Shop />} />
        <Route path="products/:id" element={<ProductDetail />} />
        <Route path="stylists" element={<Stylists />} />
        <Route path="stylists/:id" element={<StylistDetail />} />
        <Route path="privacy" element={<Privacy />} />
        <Route path="terms" element={<Terms />} />
        <Route path="returns" element={<Returns />} />
        <Route path="about" element={<About />} />
        <Route path="help" element={<Faq />} />
        <Route path="contact" element={<Contact />} />
        <Route element={<ProtectedRoute />}>
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="account" element={<Account />} />
          <Route path="wallet" element={<Wallet />} />
          <Route path="rewards" element={<Rewards />} />
          <Route path="consultations" element={<Consultations />} />
          <Route path="consultations/:id" element={<ConsultationDetail />} />
          <Route path="subscriptions" element={<Subscriptions />} />
          <Route path="ai-stylist" element={<AiStylist />} />
          <Route path="wishlist" element={<Wishlist />} />
          <Route path="cart" element={<Cart />} />
          <Route path="checkout" element={<Checkout />} />
          <Route path="orders" element={<Orders />} />
          <Route path="orders/:id" element={<OrderDetail />} />
        </Route>
        <Route element={<ProtectedRoute roles={["stylist"]} />}>
          <Route path="stylist" element={<StylistDashboard />} />
          <Route path="stylist/profile" element={<StylistProfile />} />
          <Route path="stylist/consultations/:id" element={<ConsultationDetail />} />
        </Route>
        <Route element={<ProtectedRoute roles={["admin"]} />}>
          <Route element={<AdminShell />}>
            <Route path="admin" element={<AdminDashboard />} />
            <Route path="admin/orders" element={<AdminOrders />} />
            <Route path="admin/products" element={<AdminProducts />} />
            <Route path="admin/catalogue" element={<AdminCatalogue />} />
            <Route path="admin/users" element={<AdminUsers />} />
            <Route path="admin/credits" element={<AdminCredits />} />
            <Route path="admin/stylists" element={<AdminStylists />} />
            <Route path="admin/reports" element={<AdminReports />} />
          </Route>
        </Route>
        <Route path="*" element={<ComingSoon title="Page not found" />} />
      </Route>
    </Routes>
  );
}
