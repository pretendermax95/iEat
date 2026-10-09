package com.ieat.app;

import android.app.Activity;
import android.os.Bundle;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.ValueCallback;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.JavascriptInterface;
import android.database.sqlite.SQLiteDatabase;
import android.database.Cursor;
import android.content.ContentValues;
import android.content.SharedPreferences;
import org.json.*;
import java.io.*;
import java.security.*;
import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;
import java.util.*;

public class MainActivity extends Activity {
    private WebView web;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(0xfffa5b35);
        getWindow().setNavigationBarColor(0xff202521);
        web=new WebView(this);
        if((getApplicationInfo().flags & android.content.pm.ApplicationInfo.FLAG_DEBUGGABLE)!=0) WebView.setWebContentsDebuggingEnabled(true);
        // Apply system insets: Android 15 draws activities edge to edge.
        web.setOnApplyWindowInsetsListener(new View.OnApplyWindowInsetsListener(){ @Override public WindowInsets onApplyWindowInsets(View v,WindowInsets insets){v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom()); return insets.consumeSystemWindowInsets();}});
        setContentView(web);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.getSettings().setSupportMultipleWindows(false);
        web.addJavascriptInterface(new LocalApi(),"IEatNative");
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest r){return !"app.ieat.local".equals(r.getUrl().getHost());}
            @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest request){
                if(!"app.ieat.local".equals(request.getUrl().getHost()))return new WebResourceResponse("text/plain","UTF-8",new ByteArrayInputStream(new byte[0]));
                String path=request.getUrl().getPath();
                if(path==null||path.contains(".."))return new WebResourceResponse("text/plain","UTF-8",new ByteArrayInputStream(new byte[0]));
                if(path.equals("/"))path="/index.html";
                String mime=path.endsWith(".css")?"text/css":path.endsWith(".js")?"application/javascript":path.endsWith(".svg")?"image/svg+xml":"text/html";
                try{return new WebResourceResponse(mime,"UTF-8",getAssets().open("web"+path));}
                catch(IOException e){return new WebResourceResponse("text/plain","UTF-8",404,"Not Found",null,new ByteArrayInputStream(new byte[0]));}
            }
        });
        web.loadUrl("https://app.ieat.local/index.html");
    }
    @Override public void onBackPressed(){web.evaluateJavascript("(()=>{const m=document.getElementById('modal');if(m&&m.open){m.close();return true;}return false;})()",new ValueCallback<String>(){ @Override public void onReceiveValue(String value){if(!"true".equals(value)){if(web.canGoBack())web.goBack();else finish();}}});}
    @Override protected void onDestroy(){if(web!=null){web.removeJavascriptInterface("IEatNative");web.destroy();}super.onDestroy();}

    public class LocalApi {
        private final SQLiteDatabase db;
        private final SharedPreferences prefs;
        private long lastAttempt=0;
        LocalApi(){
            db=openOrCreateDatabase("ieat.db",MODE_PRIVATE,null);
            prefs=getSharedPreferences("session",MODE_PRIVATE);
            db.execSQL("CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,name TEXT,email TEXT UNIQUE,phone TEXT,address TEXT,password TEXT)");
            db.execSQL("CREATE TABLE IF NOT EXISTS orders(id INTEGER PRIMARY KEY,user_id INTEGER,items TEXT,total INTEGER,address TEXT,phone TEXT,note TEXT,status TEXT DEFAULT 'Принят',created TEXT DEFAULT CURRENT_TIMESTAMP)");
            db.execSQL("CREATE TABLE IF NOT EXISTS partners(id INTEGER PRIMARY KEY,name TEXT,phone TEXT,restaurant TEXT)");
        }
        JSONObject user()throws Exception{
            long id=prefs.getLong("user",-1);
            try(Cursor c=db.rawQuery("SELECT id,name,email,phone,address FROM users WHERE id=?",new String[]{String.valueOf(id)})){
                if(!c.moveToFirst())return null;
                JSONObject o=new JSONObject();o.put("id",c.getLong(0));for(int i=1;i<5;i++)o.put(c.getColumnName(i),c.getString(i));return o;
            }
        }
        String readAsset(String path)throws Exception{try(InputStream in=getAssets().open(path);ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1)out.write(b,0,n);return out.toString("UTF-8");}}
        String hash(String password,String salt)throws Exception{PBEKeySpec spec=new PBEKeySpec(password.toCharArray(),salt.getBytes("UTF-8"),120000,256);byte[] value=SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).getEncoded();spec.clearPassword();return salt+":"+android.util.Base64.encodeToString(value,android.util.Base64.NO_WRAP);}
        void require(boolean condition,String message)throws Exception{if(!condition)throw new Exception(message);}
        String field(JSONObject data,String key){return data.optString(key,"").trim();}
        @JavascriptInterface public synchronized String request(String path,String body){
            try{
                JSONObject data=new JSONObject(body);Object result;
                JSONObject u=user();
                if(path.equals("catalog")) result=new JSONObject(readAsset("catalog.json"));
                else if(path.equals("me")) result=new JSONObject().put("user",u==null?JSONObject.NULL:u);
                else if(path.equals("logout")){prefs.edit().remove("user").commit();result=new JSONObject().put("ok",true);}
                else if(path.equals("register")||path.equals("login")){
                    require(System.currentTimeMillis()-lastAttempt>800,"Подождите секунду перед повторной попыткой");lastAttempt=System.currentTimeMillis();
                    String email=field(data,"email").toLowerCase(Locale.ROOT),password=data.optString("password","");
                    require(email.matches("[^\\s@]+@[^\\s@]+\\.[^\\s@]+")&&password.length()>=8&&password.length()<=128,"Проверьте email и пароль (от 8 символов)");
                    if(path.equals("register")){
                        String name=field(data,"name");require(name.length()>=2&&name.length()<=80,"Проверьте имя");
                        ContentValues v=new ContentValues();v.put("name",name);v.put("email",email);v.put("phone","");v.put("address","");v.put("password",hash(password,UUID.randomUUID().toString()));
                        require(db.insert("users",null,v)!=-1,"Этот email уже зарегистрирован");
                    }
                    try(Cursor c=db.rawQuery("SELECT id,password FROM users WHERE email=?",new String[]{email})){
                        require(c.moveToFirst(),"Неверный email или пароль");String stored=c.getString(1);
                        require(MessageDigest.isEqual(stored.getBytes("UTF-8"),hash(password,stored.split(":")[0]).getBytes("UTF-8")),"Неверный email или пароль");
                        prefs.edit().putLong("user",c.getLong(0)).commit();
                    }
                    result=new JSONObject().put("user",user());
                }else if(path.equals("partners")){
                    String name=field(data,"name"),phone=field(data,"phone"),restaurant=field(data,"restaurant");
                    require(!name.isEmpty()&&name.length()<=150&&!restaurant.isEmpty()&&restaurant.length()<=150&&phone.matches("\\+?[\\d\\s()-]{9,20}"),"Заполните имя, ресторан и корректный телефон");
                    ContentValues v=new ContentValues();v.put("name",name);v.put("phone",phone);v.put("restaurant",restaurant);db.insertOrThrow("partners",null,v);result=new JSONObject().put("ok",true);
                }else{
                    require(u!=null,"Войдите в аккаунт");String uid=String.valueOf(u.getLong("id"));
                    if(path.equals("profile")){
                        String name=field(data,"name"),phone=field(data,"phone"),address=field(data,"address");
                        require(name.length()>=2&&name.length()<=80&&phone.matches("\\+?[\\d\\s()-]{9,20}")&&address.length()>=5&&address.length()<=300,"Проверьте имя, телефон и адрес");
                        ContentValues v=new ContentValues();v.put("name",name);v.put("phone",phone);v.put("address",address);db.update("users",v,"id=?",new String[]{uid});result=new JSONObject().put("user",user());
                    }else if(path.equals("orders")&&!data.has("items")){
                        JSONArray orders=new JSONArray();try(Cursor c=db.rawQuery("SELECT * FROM orders WHERE user_id=? ORDER BY id DESC",new String[]{uid})){
                            while(c.moveToNext()){
                                JSONObject o=new JSONObject();for(int i=0;i<c.getColumnCount();i++){String k=c.getColumnName(i);if(k.equals("items"))o.put(k,new JSONArray(c.getString(i)));else if(k.equals("id")||k.equals("total")||k.equals("user_id"))o.put(k,c.getLong(i));else o.put(k,c.getString(i));}orders.put(o);
                            }
                        }result=orders;
                    }else if(path.equals("orders")){
                        JSONArray items=data.getJSONArray("items"),catalog=new JSONObject(readAsset("catalog.json")).getJSONArray("dishes"),checked=new JSONArray();int total=0;
                        String address=field(data,"address"),phone=field(data,"phone"),note=field(data,"note");
                        require(items.length()>0&&items.length()<=30&&address.length()>=5&&address.length()<=300&&phone.matches("\\+?[\\d\\s()-]{9,20}")&&note.length()<=500,"Проверьте корзину, адрес и телефон");
                        Set<Integer> seen=new HashSet<>();
                        for(int i=0;i<items.length();i++){
                            JSONObject item=items.getJSONObject(i);int id=item.getInt("id"),qty=item.getInt("qty");JSONObject dish=null;
                            for(int j=0;j<catalog.length();j++)if(catalog.getJSONObject(j).getInt("id")==id)dish=catalog.getJSONObject(j);
                            require(dish!=null&&qty>=1&&qty<=20&&seen.add(id),"Некорректное количество блюда");
                            int price=dish.getInt("price");total+=price*qty;checked.put(new JSONObject().put("id",id).put("name",dish.getString("name")).put("price",price).put("qty",qty));
                        }
                        if(total<150)total+=15;
                        ContentValues v=new ContentValues();v.put("user_id",u.getLong("id"));v.put("items",checked.toString());v.put("total",total);v.put("address",address);v.put("phone",phone);v.put("note",note);
                        long id=db.insertOrThrow("orders",null,v);result=new JSONObject().put("id",id).put("total",total).put("status","Принят");
                    }else if(path.equals("orders/cancel")){
                        ContentValues v=new ContentValues();v.put("status","Отменён");require(db.update("orders",v,"id=? AND user_id=? AND status=?",new String[]{String.valueOf(data.getLong("id")),uid,"Принят"})==1,"Заказ не найден или уже отменён");result=new JSONObject().put("ok",true);
                    }else throw new Exception("Неизвестный запрос");
                }
                return new JSONObject().put("ok",true).put("data",result).toString();
            }catch(Exception e){try{return new JSONObject().put("ok",false).put("error",e.getMessage()==null?"Не удалось выполнить запрос":e.getMessage()).toString();}catch(Exception ignored){return "{\"ok\":false,\"error\":\"Ошибка приложения\"}";}}
        }
    }
}
